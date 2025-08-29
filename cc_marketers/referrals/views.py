# referrals/views.py
from django.views.generic import ListView, TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Count
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Referral, ReferralEarning, ReferralCode, CommissionTier

class ReferralDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'referrals/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Get or create referral code
        referral_code, created = ReferralCode.objects.get_or_create(
            user=user,
            defaults={'is_active': True}
        )
        
        # Stats
        total_referrals = Referral.objects.filter(referrer=user).count()
        total_earnings = ReferralEarning.objects.filter(
            referrer=user, status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        pending_earnings = ReferralEarning.objects.filter(
            referrer=user, status='pending'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        recent_referrals = Referral.objects.filter(referrer=user).order_by('-created_at')[:5]
        recent_earnings = ReferralEarning.objects.filter(referrer=user).order_by('-created_at')[:5]
        
        context.update({
            'referral_code': referral_code,
            'referral_link': self.request.build_absolute_uri(
                reverse('users:register') + f'?ref={referral_code.code}'
            ),
            'total_referrals': total_referrals,
            'total_earnings': total_earnings,
            'pending_earnings': pending_earnings,
            'recent_referrals': recent_referrals,
            'recent_earnings': recent_earnings,
        })
        return context

class ReferralListView(LoginRequiredMixin, ListView):
    model = Referral
    template_name = 'referrals/referral_list.html'
    context_object_name = 'referrals'
    paginate_by = 20
    
    def get_queryset(self):
        return Referral.objects.filter(referrer=self.request.user).order_by('-created_at')

class EarningsListView(LoginRequiredMixin, ListView):
    model = ReferralEarning
    template_name = 'referrals/earnings_list.html'
    context_object_name = 'earnings'
    paginate_by = 20
    
    def get_queryset(self):
        return ReferralEarning.objects.filter(
            referrer=self.request.user
        ).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context['earnings_summary'] = {
            'total': ReferralEarning.objects.filter(
                referrer=user, status__in=['approved', 'paid']
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'pending': ReferralEarning.objects.filter(
                referrer=user, status='pending'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'paid': ReferralEarning.objects.filter(
                referrer=user, status='paid'
            ).aggregate(total=Sum('amount'))['total'] or 0,
        }
        return context

class CommissionTiersView(TemplateView):
    template_name = 'referrals/commission_tiers.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tiers = CommissionTier.objects.filter(
            is_active=True
        ).order_by('level', 'earning_type')

        # Attach display_rate for each tier
        for tier in tiers:
            if tier.earning_type == "task_completion":
                tier.display_rate = f"${tier.rate * 0.50:.2f} per $50 task"
            elif tier.earning_type == "advertiser_funding":
                tier.display_rate = f"${tier.rate:.0f} per $1000 funding"
            elif tier.earning_type == "signup":
                tier.display_rate = f"${tier.rate * 0.10:.2f} per signup"
            else:
                tier.display_rate = "Varies by amount"

        context['commission_tiers'] = tiers
        return context

# Admin Views
class AdminReferralDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'referrals/admin_dashboard.html'
    
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Overall stats
        total_users = User.objects.count()
        total_referrals = Referral.objects.count()
        total_earnings = ReferralEarning.objects.aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        pending_earnings = ReferralEarning.objects.filter(
            status='pending'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Top referrers
        top_referrers = User.objects.annotate(
            referral_count=Count('referrals_made'),
            total_earned=Sum('referral_earnings__amount')
        ).filter(referral_count__gt=0).order_by('-referral_count')[:10]
        
        # Recent activity
        recent_referrals = Referral.objects.order_by('-created_at')[:10]
        recent_earnings = ReferralEarning.objects.order_by('-created_at')[:10]
        
        context.update({
            'total_users': total_users,
            'total_referrals': total_referrals,
            'total_earnings': total_earnings,
            'pending_earnings': pending_earnings,
            'top_referrers': top_referrers,
            'recent_referrals': recent_referrals,
            'recent_earnings': recent_earnings,
        })
        return context

class AdminEarningsManagementView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = ReferralEarning
    template_name = 'referrals/admin_earnings.html'
    context_object_name = 'earnings'
    paginate_by = 50
    
    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser
    
    def get_queryset(self):
        queryset = ReferralEarning.objects.all().order_by('-created_at')
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_filter'] = self.request.GET.get('status', '')
        return context