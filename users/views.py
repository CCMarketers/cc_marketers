# users/views.py
import logging
import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import LoginView, PasswordResetView
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.http import urlsafe_base64_decode
from django.views.generic import (
    CreateView,
    UpdateView,
    TemplateView,
    FormView,
    RedirectView,
    DetailView,
    View,
)


from .forms import (
    CustomUserCreationForm,
    CustomAuthenticationForm,
    UserProfileForm,
    PhoneVerificationForm,
    PhoneVerificationCodeForm,
    PasswordChangeForm,
    ExtendedProfileForm,
)
from .models import User, UserProfile, EmailVerificationToken, PhoneVerificationToken

from tasks.models import Task, Submission
from referrals.models import ReferralCode, Referral
from core.services import send_verification_email
from wallets.services import WalletService
from payments.models import PaymentTransaction


logger = logging.getLogger(__name__)

# -------------------------
# Helper utilities
# -------------------------
def get_or_create_profile(user: User) -> UserProfile:
    """
    Centralized helper to get or create a user's UserProfile.
    This avoids repeated get_or_create scattered in views.
    """
    profile, _created = UserProfile.objects.get_or_create(user=user)
    return profile


def safe_send_verification_email(user: User) -> bool:
    """
    Wrap the email sending call and log if it fails.
    Returns True on success, False on failure.
    """
    try:
        return send_verification_email(user)
    except Exception as exc:
        logger.exception("Failed to send verification email for user %s: %s", user.pk, exc)
        return False


# -------------------------
# Registration & Auth
# -------------------------
class UserRegistrationView(CreateView):
    """User registration with referral tracking"""
    model = User
    form_class = CustomUserCreationForm
    template_name = "users/register.html"
    success_url = reverse_lazy("users:profile_setup")

    def get_initial(self):
        initial = super().get_initial()
        if ref := self.request.GET.get("ref"):
            initial["referral_code"] = ref
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        user: User = self.object

        # --- Referral handling (use select_related to avoid extra hits later) ---
        ref_code = self.request.GET.get("ref") or form.cleaned_data.get("referral_code")
        if ref_code:
            try:
                ref_obj = ReferralCode.objects.select_related("user").get(code=ref_code)
                referrer = ref_obj.user
                Referral.objects.get_or_create(
                    referrer=referrer,
                    referred=user,
                    defaults={"level": 1, "referral_code": ref_obj},
                )
            except ReferralCode.DoesNotExist:
                logger.debug("Registration used unknown referral code: %s", ref_code)

        # --- Login user and send verification email ---
        login(self.request, user)
        success = safe_send_verification_email(user)
        if success:
            messages.success(self.request, "Welcome! Please verify your email.")
        else:
            messages.warning(self.request, "Welcome! We couldn't send a verification email — please try resending it.")

        return response


class CustomLoginView(LoginView):
    """Custom login supporting email/phone authentication"""
    form_class = CustomAuthenticationForm
    template_name = "users/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        # 1. Honor ?next= param if present
        next_url = self.request.GET.get("next")
        if next_url:
            return next_url

        # 2. account_type-based redirects
        account_type = getattr(self.request.user, "account_type", None)

        redirect_map = {
            User.ADMIN: reverse_lazy("users:dashboard"),
            User.MEMBERS: reverse_lazy("tasks:my_tasks"),
            User.DEMO: reverse_lazy("tasks:task_list"),
        }
        return redirect_map.get(account_type, reverse_lazy("tasks:task_list"))

    def form_valid(self, form):
        # welcome message and delegating to parent for auth flow
        try:
            name = form.get_user().get_short_name()
        except Exception:
            name = form.get_user().username
        messages.success(self.request, f"Welcome back, {name}!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Invalid login credentials. Please try again.")
        logger.info("Failed login attempt for identifier: %s", form.data.get("username") or form.data.get("email"))
        return super().form_invalid(form)


class UserLogoutView(RedirectView):
    """Handle user logout (keeps compatibility with existing GET-based flow)."""
    url = reverse_lazy("users:login")

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        logout(request)
        messages.info(request, "You have been logged out.")
        return super().get(request, *args, **kwargs)


# -------------------------
# Profile setup & management
# -------------------------
class ProfileSetupView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserProfileForm
    template_name = "users/profile_setup.html"
    success_url = reverse_lazy("users:dashboard")

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_or_create_profile(self.request.user)
        context["extended_profile"] = profile
        return context

    def form_valid(self, form):
        # Save user fields
        response = super().form_valid(form)

        # Update profile fields in a controlled way (avoid pulling from raw POST)
        profile = get_or_create_profile(self.request.user)
        changed = False
        for field in ("location", "skills"):
            if field in form.cleaned_data:
                setattr(profile, field, form.cleaned_data.get(field) or getattr(profile, field))
                changed = True
        if changed:
            profile.save(update_fields=[f for f in ("location", "skills") if getattr(profile, f) is not None])

        messages.success(self.request, "Profile setup saved.")
        return response


class UserProfileView(LoginRequiredMixin, UpdateView):
    """User profile management (edit & update profile)."""
    model = User
    form_class = UserProfileForm
    template_name = "users/profile.html"
    success_url = reverse_lazy("users:profile")

    def get_object(self):
        return self.request.user

    def get_profile(self):
        return get_or_create_profile(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = self.get_profile()
        context["extended_profile"] = profile
        context["extended_form"] = ExtendedProfileForm(instance=profile)
        context["profile"] = profile
        context["profile_form"] = context["extended_form"]

        # Referral statistics — prefer cached properties if you have them on User
        context["referral_stats"] = {
            "total_referrals": getattr(self.request.user, "total_referrals", 0),
            "active_referrals": getattr(self.request.user, "active_referrals", 0),
            "referral_url": getattr(self.request.user, "referral_url", ""),
        }
        return context

    def post(self, request, *args, **kwargs):
        """
        Process both the User form and the ExtendedProfileForm.
        """
        self.object = self.get_object()
        user_form = self.get_form()
        profile = self.get_profile()
        extended_form = ExtendedProfileForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and extended_form.is_valid():
            return self.forms_valid(user_form, extended_form)
        else:
            return self.forms_invalid(user_form, extended_form)

    def forms_valid(self, user_form, extended_form):
        user_form.save()
        extended_form.save()
        messages.success(self.request, "Profile updated successfully!")
        return redirect(self.get_success_url())

    def forms_invalid(self, user_form, extended_form):
        context = self.get_context_data(form=user_form)
        context["extended_form"] = extended_form
        context["profile_form"] = extended_form
        return self.render_to_response(context)


class PublicProfileView(DetailView):
    """Public-facing user profile page."""
    model = User
    template_name = "users/public_profile.html"
    context_object_name = "profile_user"
    slug_field = "username"
    slug_url_kwarg = "username"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile = get_or_create_profile(self.object)
        context["extended_profile"] = profile
        return context


# -------------------------
# Dashboard (optimized)
# -------------------------
class UserDashboardView(LoginRequiredMixin, TemplateView):
    """User dashboard with caching and prefetching where appropriate."""
    template_name = "users/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Cache key per-user for short period to avoid heavy DB hits on high traffic
        cache_key = f"user_dashboard_{user.pk}"
        cached = cache.get(cache_key)
        if cached:
            context.update(cached)
            return context

        # User stats (keep minimal DB hits; assume some properties may be cached on the User model)
        user_stats = {
            "total_referrals": getattr(user, "total_referrals", 0),
            "active_referrals": getattr(user, "active_referrals", 0),
            "member_since": getattr(user, "date_joined", None),
            "email_verified": getattr(user, "email_verified", False),
            "phone_verified": getattr(user, "phone_verified", False),
        }

        # Recent referrals (select_related to avoid N+1 if displaying referrer info)
        recent_referrals_qs = getattr(user, "referrals", None)
        if recent_referrals_qs is None:
            recent_referrals = []
        else:
            recent_referrals = recent_referrals_qs.select_related("referrer")[:5]

        # Recent submissions by the user (select_related for task)
        recent_tasks = (
            Submission.objects.filter(member=user)
            .select_related("task")
            .order_by("-submitted_at")[:5]
        )

        # Completed tasks count
        completed_tasks_count = Submission.objects.filter(member=user, status="approved").count()

        # Active tasks count (determine account_type quickly)
        if Task.objects.filter(advertiser=user).exists():
            active_tasks_count = Task.objects.filter(advertiser=user, status="active").count()
        else:
            active_tasks_count = Submission.objects.filter(member=user, status="pending").count()

        # Referral code/link
        referral_code, _ = ReferralCode.objects.get_or_create(user=user, defaults={"is_active": True})
        referral_link = self.request.build_absolute_uri(reverse_lazy("users:register") + f"?ref={referral_code.code}")

        # Wallets and balances
        wallet = WalletService.get_or_create_wallet(user)
        # pending_withdrawals = wallet.get_pending_withdrawals
        try:
            available_balance = wallet.get_available_balance()

        except Exception:
            logger.exception("Error computing available balance for user %s", user.pk)
            available_balance = Decimal("0.00")


        # Recent transactions (deterministic order)
        recent_transactions = PaymentTransaction.objects.filter(user=user).order_by("-created_at")[:10]

        # Wallet balances (fall back to 0.00 if missing)
        main_wallet_balance = getattr(getattr(user, "wallet", None), "balance", Decimal("0.00"))
        task_wallet_balance = getattr(getattr(user, "taskwallet", None), "balance", Decimal("0.00"))

        dashboard_data = {
            "user_stats": user_stats,
            "recent_referrals": recent_referrals,
            "recent_tasks": recent_tasks,
            "completed_tasks_count": completed_tasks_count,
            "active_tasks_count": active_tasks_count,
            "referral_code": referral_code,
            "referral_link": referral_link,
            "main_wallet_balance": main_wallet_balance,
            "task_wallet_balance": task_wallet_balance,
            "available_balance": available_balance,
            "recent_transactions": recent_transactions,
        }

        # Cache for a short period (e.g., 30 seconds) — tune as needed
        cache.set(cache_key, dashboard_data, 30)

        context.update(dashboard_data)
        return context


# -------------------------
# Email verification flows
# -------------------------
class EmailVerificationView(TemplateView):
    template_name = "users/email_verification.html"

    def get(self, request: HttpRequest, uidb64: str, token: str, *args, **kwargs):
        user = None
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            uid = uuid.UUID(uid)
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist, AttributeError) as exc:
            logger.debug("Invalid email verification link: %s (%s)", uidb64, exc)
            user = None

        if user is not None and default_token_generator.check_token(user, token):
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            messages.success(request, "Email verified successfully!")
            return redirect("users:dashboard" if request.user.is_authenticated else "users:login")

        messages.error(request, "Invalid or expired verification link.")
        return render(request, self.template_name)


class ResendVerificationView(LoginRequiredMixin, TemplateView):
    """Resend email verification"""
    template_name = "users/resend_verification.html"

    def post(self, request: HttpRequest, *args, **kwargs):
        user = request.user
        if user.email_verified:
            messages.info(request, "Your email is already verified.")
            return redirect("users:dashboard")

        # Clean up existing tokens and send again
        EmailVerificationToken.objects.filter(user=user, used=False).delete()
        success = safe_send_verification_email(user)
        if success:
            messages.success(request, "Verification email sent!")
        else:
            messages.error(request, "Failed to send verification email. Please try again later.")
        return redirect("users:dashboard")


# -------------------------
# Phone verification
# -------------------------
class PhoneVerificationView(LoginRequiredMixin, FormView):
    """Phone number verification (sends verification token)."""
    form_class = PhoneVerificationForm
    template_name = "users/phone_verification.html"
    success_url = reverse_lazy("users:phone_verify_code")

    def form_valid(self, form):
        user = self.request.user
        phone = form.cleaned_data["phone"]
        user.phone = phone
        user.save(update_fields=["phone"])
        PhoneVerificationToken.objects.filter(user=user, used=False).delete()
        token = PhoneVerificationToken.objects.create(user=user)
        # TODO: integrate actual SMS sending service and log result
        logger.debug("Created phone verification token %s for user %s", token.pk, user.pk)
        messages.success(self.request, f"Code sent to {phone}")
        return super().form_valid(form)


class PhoneVerificationCodeView(LoginRequiredMixin, FormView):
    """Verify phone with code"""
    form_class = PhoneVerificationCodeForm
    template_name = "users/phone_verification_code.html"
    success_url = reverse_lazy("users:dashboard")

    def form_valid(self, form):
        user = self.request.user
        code = form.cleaned_data["code"]
        try:
            token = PhoneVerificationToken.objects.get(user=user, token=code, used=False)
        except PhoneVerificationToken.DoesNotExist:
            form.add_error("code", "Invalid code.")
            return self.form_invalid(form)

        if not token.is_valid():
            form.add_error("code", "Verification code expired.")
            return self.form_invalid(form)

        user.phone_verified = True
        user.save(update_fields=["phone_verified"])
        token.used = True
        token.save(update_fields=["used"])
        messages.success(self.request, "Phone verified successfully!")
        return super().form_valid(form)


# -------------------------
# Password change / reset
# -------------------------
class PasswordChangeView(LoginRequiredMixin, FormView):
    """Change password"""
    form_class = PasswordChangeForm
    template_name = "users/password_change.html"
    success_url = reverse_lazy("users:profile")

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def form_valid(self, form):
        user = self.request.user
        user.set_password(form.cleaned_data["new_password1"])
        user.save(update_fields=["password"])
        # Prevent the user from being logged out by updating session auth hash
        update_session_auth_hash(self.request, user)
        messages.success(self.request, "Password changed successfully!")
        return super().form_valid(form)


class CustomPasswordResetView(PasswordResetView):
    template_name = "users/password_reset.html"
    email_template_name = "users/password_reset_email.html"
    subject_template_name = "users/password_reset_subject.txt"
    success_url = reverse_lazy("users:password_reset_done")

    def send_mail(
        self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None
    ):
        subject = render_to_string(subject_template_name, context).strip()
        body = render_to_string(email_template_name, context)
        email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name:
            html_email = render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, "text/html")
        try:
            email_message.send()
        except Exception as exc:
            logger.exception("Password reset email failed to %s: %s", to_email, exc)


# -------------------------
# Lightweight API endpoints (GET-only)
# -------------------------
class CheckEmailAvailabilityView(View):
    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        email = request.GET.get("email")
        if not email:
            return JsonResponse({"available": False, "message": "Email required"}, status=400)
        exists = User.objects.filter(email__iexact=email).exists()
        return JsonResponse({"available": not exists, "message": "Email available" if not exists else "Email taken"})


class CheckPhoneAvailabilityView(View):
    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        phone = request.GET.get("phone")
        if not phone:
            return JsonResponse({"available": False, "message": "Phone required"}, status=400)
        exists = User.objects.filter(phone=phone).exists()
        return JsonResponse({"available": not exists, "message": "Phone available" if not exists else "Phone taken"})


class ValidateReferralCodeView(View):
    def get(self, request: HttpRequest, *args, **kwargs) -> JsonResponse:
        code = request.GET.get("code")
        if not code:
            return JsonResponse({"valid": False, "message": "Code required"}, status=400)

        ref_code = ReferralCode.objects.filter(code=code).select_related("user").first()
        if not ref_code:
            return JsonResponse({"valid": False, "message": "Invalid referral code"})
        referrer = ref_code.user
        return JsonResponse(
            {
                "valid": True,
                "message": f"Valid referral from {referrer.get_display_name()}",
                "referrer": {"username": referrer.username, "email": referrer.email},
            }
        )


def landing_page(request):
    return render(request, "users/landing.html")


def help_center(request):
    return render(request, "users/helpcenter.html")

def contact(request):
    return render(request, "users/contact.html")

def terms(request):
    return render(request, "users/terms.html")

def privacy(request):
    return render(request, "users/privacy.html")