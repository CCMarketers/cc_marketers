# users/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.views.generic import (
    CreateView, UpdateView, TemplateView, FormView, RedirectView, DetailView
)
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncMonth
from tasks.models import Task, Submission

from .models import User, UserProfile, EmailVerificationToken, PhoneVerificationToken
from .forms import (
    CustomUserCreationForm, CustomAuthenticationForm, UserProfileForm,
    PhoneVerificationForm, PhoneVerificationCodeForm, PasswordChangeForm, 
    ExtendedProfileForm
)

# ---------- UTILS ----------
def send_verification_email(request, user):
    """Helper to send email verification"""
    token = EmailVerificationToken.objects.create(user=user)
    verification_url = request.build_absolute_uri(
        reverse('users:verify_email', kwargs={'token': token.token})
    )
    send_mail(
        subject='Verify your TaskPlatform account',
        message=f'Click this link to verify your account: {verification_url}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=True
    )


# ---------- VIEWS ----------
class UserRegistrationView(CreateView):
    """User registration with referral tracking"""
    model = User
    form_class = CustomUserCreationForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:profile_setup')

    def get_initial(self):
        initial = super().get_initial()
        if ref := self.request.GET.get('ref'):
            initial['referral_code'] = ref
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        login(self.request, user)
        send_verification_email(self.request, user)
        messages.success(self.request, 'Welcome! Please verify your email.')
        return response


class CustomLoginView(LoginView):
    """Custom login supporting email/phone authentication"""
    form_class = CustomAuthenticationForm
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        role = getattr(self.request.user, 'role', None)
        return {
            User.ADMIN: reverse_lazy('admin:index'),
            User.ADVERTISER: reverse_lazy('tasks:my_tasks'),
            User.MEMBER: reverse_lazy('tasks:task_list'),
        }.get(role, reverse_lazy('tasks:task_list'))

    def form_valid(self, form):
        messages.success(self.request, f'Welcome back, {form.get_user().get_short_name()}!')
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Invalid login credentials. Please try again.")
        return super().form_invalid(form)

class UserLogoutView(RedirectView):
    """Handle user logout"""
    url = reverse_lazy('users:login')

    def get(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, 'You have been logged out.')
        return super().get(request, *args, **kwargs)


class ProfileSetupView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = "users/profile_setup.html"
    success_url = reverse_lazy("users:dashboard")

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        context["extended_profile"] = profile
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        # Save UserProfile data
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        profile.location = self.request.POST.get("location", "")
        profile.skills = self.request.POST.get("skills", "")
        profile.save()

        return response


class UserDashboardView(LoginRequiredMixin, TemplateView):
    """User dashboard"""
    template_name = 'users/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # User stats
        user_stats = {
            "total_referrals": getattr(user, "total_referrals", 0),
            "active_referrals": getattr(user, "active_referrals", 0),
            "member_since": getattr(user, "date_joined", None),
            "email_verified": getattr(user, "email_verified", False),
            "phone_verified": getattr(user, "phone_verified", False),
        }

        # Recent referrals
        recent_referrals = getattr(user, "referrals", None)
        if recent_referrals:
            recent_referrals = recent_referrals.all()[:5]
        else:
            recent_referrals = []

        # Recent tasks created (advertiser view)
        # Recent submissions by the user
        recent_tasks = (
            Submission.objects.filter(member=user)
            .select_related("task")
            .order_by("-submitted_at")[:5]
        )


        # Completed tasks (approved submissions by this user)
        completed_tasks_count = Submission.objects.filter(
            member=user, status="approved"
        ).count()

        # Active tasks: if advertiser → their active tasks, else → user's pending submissions
        if Task.objects.filter(advertiser=user).exists():  # advertiser
            active_tasks_count = Task.objects.filter(advertiser=user, status="active").count()
        else:  # member
            active_tasks_count = Submission.objects.filter(member=user, status="pending").count()

        context.update({
            "user_stats": user_stats,
            "recent_referrals": recent_referrals,
            "recent_tasks": recent_tasks,
            "completed_tasks_count": completed_tasks_count,
            "active_tasks_count": active_tasks_count,
        })
        return context


class EmailVerificationView(TemplateView):
    """Email verification"""
    template_name = 'users/email_verification.html'

    def get(self, request, token):
        try:
            verification_token = EmailVerificationToken.objects.select_related("user").get(token=token)
            if verification_token.is_valid():
                user = verification_token.user
                user.email_verified = True
                user.save(update_fields=["email_verified"])
                verification_token.used = True
                verification_token.save(update_fields=["used"])
                messages.success(request, 'Email verified successfully!')
                return redirect('users:dashboard' if request.user.is_authenticated else 'users:login')
            messages.error(request, 'Verification link expired or used.')
        except EmailVerificationToken.DoesNotExist:
            messages.error(request, 'Invalid verification link.')
        return render(request, self.template_name)


class ResendVerificationView(LoginRequiredMixin, TemplateView):
    """Resend email verification"""
    template_name = 'users/resend_verification.html'

    def post(self, request):
        user = request.user
        if user.email_verified:
            messages.info(request, 'Your email is already verified.')
            return redirect('users:dashboard')
        EmailVerificationToken.objects.filter(user=user, used=False).delete()
        send_verification_email(request, user)
        messages.success(request, 'Verification email sent!')
        return redirect('users:dashboard')


class PhoneVerificationView(LoginRequiredMixin, FormView):
    """Phone number verification"""
    form_class = PhoneVerificationForm
    template_name = 'users/phone_verification.html'
    success_url = reverse_lazy('users:phone_verify_code')

    def form_valid(self, form):
        user = self.request.user
        phone = form.cleaned_data['phone']
        user.phone = phone
        user.save(update_fields=["phone"])
        PhoneVerificationToken.objects.filter(user=user, used=False).delete()
        PhoneVerificationToken.objects.create(user=user)
        # send_sms(phone, f'Your code is: {token.token}')  # Implement SMS
        messages.success(self.request, f'Code sent to {phone}')
        return super().form_valid(form)


class PhoneVerificationCodeView(LoginRequiredMixin, FormView):
    """Verify phone with code"""
    form_class = PhoneVerificationCodeForm
    template_name = 'users/phone_verification_code.html'
    success_url = reverse_lazy('users:dashboard')

    def form_valid(self, form):
        user, code = self.request.user, form.cleaned_data['code']
        try:
            token = PhoneVerificationToken.objects.get(user=user, token=code, used=False)
            if token.is_valid():
                user.phone_verified = True
                user.save(update_fields=["phone_verified"])
                token.used = True
                token.save(update_fields=["used"])
                messages.success(self.request, 'Phone verified successfully!')
                return super().form_valid(form)
            form.add_error('code', 'Verification code expired.')
        except PhoneVerificationToken.DoesNotExist:
            form.add_error('code', 'Invalid code.')
        return self.form_invalid(form)


class PasswordChangeView(LoginRequiredMixin, FormView):
    """Change password"""
    form_class = PasswordChangeForm
    template_name = 'users/password_change.html'
    success_url = reverse_lazy('users:profile')

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'user': self.request.user}

    def form_valid(self, form):
        user = self.request.user
        user.set_password(form.cleaned_data['new_password1'])
        user.save(update_fields=["password"])
        login(self.request, user)
        messages.success(self.request, 'Password changed successfully!')
        return super().form_valid(form)


class ReferralSignupView(UserRegistrationView):
    """Referral signup"""
    template_name = 'users/referral_signup.html'

    def get_initial(self):
        initial = super().get_initial()
        if code := self.kwargs.get('code'):
            initial['referral_code'] = code
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        code = self.kwargs.get('code')
        try:
            context['referrer'] = User.objects.only("username").get(referral_code=code)
        except User.DoesNotExist:
            context['invalid_referral'] = True
        return context


class ReferralDashboardView(LoginRequiredMixin, TemplateView):
    """Referral dashboard"""
    template_name = 'users/referral_dashboard.html'

    def get_context_data(self, **kwargs):
        user = self.request.user
        referrals = user.referrals.all()
        monthly_stats = (
            referrals.annotate(month=TruncMonth('date_joined'))
            .values('month').annotate(count=Count('id'))
            .order_by('-month')[:12]
        )
        return {
            **super().get_context_data(**kwargs),
            'referral_stats': {
                'total_referrals': referrals.count(),
                'active_referrals': referrals.filter(is_active=True).count(),
                'verified_referrals': referrals.filter(email_verified=True).count(),
                'referral_code': user.referral_code,
                'referral_url': user.referral_url,
            },
            'recent_referrals': referrals.order_by('-date_joined')[:10],
            'monthly_stats': monthly_stats,
        }


# ---------- API VIEWS ----------
class CheckEmailAvailabilityView(TemplateView):
    def get(self, request):
        email = request.GET.get('email')
        if not email:
            return JsonResponse({'available': False, 'message': 'Email required'})
        exists = User.objects.filter(email=email).exists()
        return JsonResponse({
            'available': not exists,
            'message': 'Email available' if not exists else 'Email taken'
        })


class CheckPhoneAvailabilityView(TemplateView):
    def get(self, request):
        phone = request.GET.get('phone')
        if not phone:
            return JsonResponse({'available': False, 'message': 'Phone required'})
        exists = User.objects.filter(phone=phone).exists()
        return JsonResponse({
            'available': not exists,
            'message': 'Phone available' if not exists else 'Phone taken'
        })


class ValidateReferralCodeView(TemplateView):
    def get(self, request):
        code = request.GET.get('code')
        if not code:
            return JsonResponse({'valid': False, 'message': 'Code required'})
        try:
            referrer = User.objects.only("username").get(referral_code=code)
            return JsonResponse({
                'valid': True,
                'message': f'Valid referral from {referrer.get_display_name()}',
                'referrer': {'name': referrer.get_display_name(), 'username': referrer.username}
            })
        except User.DoesNotExist:
            return JsonResponse({'valid': False, 'message': 'Invalid referral code'})



class UserProfileView(LoginRequiredMixin, UpdateView):
    """User profile management (edit & update profile)."""
    model = User
    form_class = UserProfileForm
    template_name = "users/profile.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Ensure extended profile exists
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        context["extended_profile"] = profile
        context["extended_form"] = ExtendedProfileForm(instance=profile)

        # Referral statistics (optimize by avoiding redundant lookups)
        context["referral_stats"] = {
            "total_referrals": getattr(self.request.user, "total_referrals", 0),
            "active_referrals": getattr(self.request.user, "active_referrals", 0),
            "referral_url": getattr(self.request.user, "referral_url", ""),
        }

        return context

    def form_valid(self, form):
        """Save both User and Extended Profile."""
        response = super().form_valid(form)

        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        extended_form = ExtendedProfileForm(self.request.POST, instance=profile)
        if extended_form.is_valid():
            extended_form.save()

        messages.success(self.request, "Profile updated successfully!")
        return response


class PublicProfileView(DetailView):
    """Public-facing user profile page."""
    model = User
    template_name = "users/public_profile.html"
    context_object_name = "profile_user"
    slug_field = "username"
    slug_url_kwarg = "username"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Preload extended profile to minimize queries
        profile, _ = UserProfile.objects.get_or_create(user=self.object)
        context["extended_profile"] = profile
        return context

