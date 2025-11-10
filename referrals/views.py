import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Count, Q
from django.urls import reverse
from django.views.generic import ListView, TemplateView
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import Referral, ReferralEarning, ReferralCode, CommissionTier
from .services import ReferralValidator

logger = logging.getLogger(__name__)
User = get_user_model()


class ReferralDashboardView(LoginRequiredMixin, TemplateView):
    """User dashboard for viewing referral stats."""
    template_name = "referrals/dashboard.html"

    def get_context_data(self, **kwargs):
        from subscriptions.services import SubscriptionService
        
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        logger.info(f"[DASHBOARD] Loading dashboard for user: {user.username}")

        # Get or create referral code
        referral_code, created = ReferralCode.objects.get_or_create(
            user=user, 
            defaults={"is_active": True, "can_refer": True}
        )
        
        if created:
            logger.info(f"[DASHBOARD] Created new referral code for {user.username}")

        # Get user's subscription info
        user_subscription = SubscriptionService.get_user_active_subscription(user)
        subscription_type = user_subscription.plan.name if user_subscription else "None"
        
        logger.debug(f"[DASHBOARD] {user.username} subscription type: {subscription_type}")
        
        # Calculate referral limits based on subscription
        demo_referral_count = 0
        demo_referral_limit = 0
        can_refer_demo = False
        can_refer_business = False
        
        if subscription_type == "Business Member Account":
            demo_referral_count = referral_code.get_active_demo_referral_count()
            demo_referral_limit = ReferralValidator.MAX_DEMO_REFERRALS
            can_refer_demo = demo_referral_count < demo_referral_limit
            can_refer_business = True
            logger.debug(
                f"[DASHBOARD] Business member {user.username}: {demo_referral_count}/{demo_referral_limit} Demo slots"
            )
        elif subscription_type == "Demo Account":
            can_refer_demo = False
            can_refer_business = True
            logger.debug(f"[DASHBOARD] Demo member {user.username}: Can only refer Business")

        # Pre-calculate stats with aggregation
        approved_qs = ReferralEarning.objects.filter(
            referrer=user, status__in=["approved", "paid"]
        )
        pending_qs = ReferralEarning.objects.filter(referrer=user, status="pending")

        # Get referral breakdown
        total_referrals = Referral.objects.filter(referrer=user, is_active=True)
        direct_referrals = total_referrals.filter(level=1)
        indirect_referrals = total_referrals.filter(level=2)
        
        total_earnings = approved_qs.aggregate(total=Sum("amount"))["total"] or 0
        pending_earnings = pending_qs.aggregate(total=Sum("amount"))["total"] or 0
        
        logger.info(
            f"[DASHBOARD] {user.username} stats - Referrals: {total_referrals.count()} "
            f"(L1: {direct_referrals.count()}, L2: {indirect_referrals.count()}), "
            f"Earnings: ₦{total_earnings}, Pending: ₦{pending_earnings}"
        )

        context.update({
            "referral_code": referral_code,
            "referral_link": self.request.build_absolute_uri(
                reverse("users:register") + f"?ref={referral_code.code}"
            ),
            "subscription_type": subscription_type,
            "can_refer": referral_code.can_refer,
            "can_refer_demo": can_refer_demo,
            "can_refer_business": can_refer_business,
            "demo_referral_count": demo_referral_count,
            "demo_referral_limit": demo_referral_limit,
            "total_referrals": total_referrals.count(),
            "direct_referrals_count": direct_referrals.count(),
            "indirect_referrals_count": indirect_referrals.count(),
            "total_earnings": total_earnings,
            "pending_earnings": pending_earnings,
            "recent_referrals": Referral.objects.filter(referrer=user)
            .select_related("referred")
            .order_by("-created_at")[:5],
            "recent_earnings": ReferralEarning.objects.filter(referrer=user)
            .select_related("referral")
            .order_by("-created_at")[:5],
        })
        return context


class ReferralListView(LoginRequiredMixin, ListView):
    """List of all referrals made by the current user."""
    model = Referral
    template_name = "referrals/referral_list.html"
    context_object_name = "referrals"
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        logger.info(f"[REFERRAL_LIST] Loading referral list for user: {user.username}")
        
        return (
            Referral.objects.filter(referrer=user)
            .select_related("referred")
            .order_by("-created_at")
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add subscription type for each referral
        from subscriptions.services import SubscriptionService
        for referral in context['referrals']:
            user_sub = SubscriptionService.get_user_active_subscription(referral.referred)
            referral.current_subscription = user_sub.plan.name if user_sub else "No Subscription"
        
        logger.debug(f"[REFERRAL_LIST] Loaded {len(context['referrals'])} referrals")
        return context


class EarningsListView(LoginRequiredMixin, ListView):
    """List of all referral earnings for the current user."""
    model = ReferralEarning
    template_name = "referrals/earnings_list.html"
    context_object_name = "earnings"
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        logger.info(f"[EARNINGS_LIST] Loading earnings list for user: {user.username}")
        
        return (
            ReferralEarning.objects.filter(referrer=user)
            .select_related("referral", "referred_user")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        earnings_qs = ReferralEarning.objects.filter(referrer=user)
        context["earnings_summary"] = {
            "total": earnings_qs.filter(status__in=["approved", "paid"])
            .aggregate(total=Sum("amount"))["total"] or 0,
            "pending": earnings_qs.filter(status="pending")
            .aggregate(total=Sum("amount"))["total"] or 0,
            "paid": earnings_qs.filter(status="paid")
            .aggregate(total=Sum("amount"))["total"] or 0,
        }
        
        logger.info(
            f"[EARNINGS_LIST] {user.username} earnings summary: "
            f"Total: ₦{context['earnings_summary']['total']}, "
            f"Pending: ₦{context['earnings_summary']['pending']}, "
            f"Paid: ₦{context['earnings_summary']['paid']}"
        )
        
        return context


class CommissionTiersView(TemplateView):
    """Public view showing commission tiers and rules."""
    template_name = "referrals/commission_tiers.html"

    def get_context_data(self, **kwargs):
        logger.info("[COMMISSION_TIERS] Loading commission tiers page")
        
        context = super().get_context_data(**kwargs)
        
        # Display flat signup bonuses
        context["referral_rules"] = {
            "level_1_bonus": "₦5,000",
            "level_2_bonus": "₦3,000",
            "demo_can_refer": "Business Members only",
            "business_can_refer": "Up to 10 Demo users + unlimited Business Members",
            "max_levels": 2,
        }
        
        # Get active commission tiers for other earning types (if any)
        tiers = CommissionTier.objects.filter(
            is_active=True,
            level__lte=2
        ).order_by("level", "earning_type")

        logger.debug(f"[COMMISSION_TIERS] Found {tiers.count()} active commission tiers")
        context["commission_tiers"] = tiers
        return context


# API Endpoint for Frontend Validation
@method_decorator(csrf_exempt, name='dispatch')
class CheckReferralEligibilityView(View):
    """
    API endpoint to check referral eligibility before registration.
    
    POST /referrals/api/check-eligibility/
    Body: {
        "referral_code": "ABC12345",
        "subscription_type": "Business Member Account"
    }
    """
    
    def post(self, request, *args, **kwargs):
        import json
        
        client_ip = request.META.get('REMOTE_ADDR', 'unknown')
        logger.info(f"[API_ELIGIBILITY] Received eligibility check from IP: {client_ip}")
        
        try:
            data = json.loads(request.body)
            referral_code = data.get('referral_code', '').strip()
            subscription_type = data.get('subscription_type', '').strip()
            
            logger.info(
                f"[API_ELIGIBILITY] Checking code: {referral_code}, "
                f"subscription: {subscription_type}"
            )
            
            if not referral_code or not subscription_type:
                logger.warning("[API_ELIGIBILITY] Missing required fields")
                return JsonResponse({
                    "eligible": False,
                    "reason": "Referral code and subscription type are required."
                }, status=400)
            
            result = ReferralValidator.check_referral_eligibility(
                referral_code,
                subscription_type
            )
            
            logger.info(
                f"[API_ELIGIBILITY] Result for {referral_code}: "
                f"{'✅ ELIGIBLE' if result['eligible'] else '❌ NOT ELIGIBLE'}"
            )
            
            return JsonResponse(result)
            
        except json.JSONDecodeError as e:
            logger.error(f"[API_ELIGIBILITY] Invalid JSON: {str(e)}")
            return JsonResponse({
                "eligible": False,
                "reason": "Invalid JSON data."
            }, status=400)
        except Exception as e:
            logger.error(
                f"[API_ELIGIBILITY] Server error: {str(e)}",
                exc_info=True
            )
            return JsonResponse({
                "eligible": False,
                "reason": f"Server error: {str(e)}"
            }, status=500)


# Admin views
class AdminReferralDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Admin dashboard for overview of all referral stats."""
    template_name = "referrals/admin_dashboard.html"

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        logger.info(f"[ADMIN_DASHBOARD] Loading admin dashboard for: {self.request.user.username}")
        
        context = super().get_context_data(**kwargs)

        # Global stats
        context["total_users"] = User.objects.count()
        context["total_referrals"] = Referral.objects.filter(is_active=True).count()
        context["level_1_referrals"] = Referral.objects.filter(level=1, is_active=True).count()
        context["level_2_referrals"] = Referral.objects.filter(level=2, is_active=True).count()
        
        total_earnings_agg = ReferralEarning.objects.aggregate(total=Sum("amount"))
        context["total_earnings"] = total_earnings_agg["total"] or 0
        
        pending_earnings_agg = ReferralEarning.objects.filter(status="pending").aggregate(
            total=Sum("amount")
        )
        context["pending_earnings"] = pending_earnings_agg["total"] or 0
        
        logger.info(
            f"[ADMIN_DASHBOARD] Global stats - Users: {context['total_users']}, "
            f"Referrals: {context['total_referrals']} (L1: {context['level_1_referrals']}, "
            f"L2: {context['level_2_referrals']}), Total Earnings: ₦{context['total_earnings']}"
        )

        # Top referrers with detailed stats
        top_referrers = (
            User.objects.annotate(
                referral_count=Count("referrals_made", distinct=True, filter=Q(referrals_made__is_active=True)),
                total_earned=Sum("referral_earnings__amount", filter=Q(referral_earnings__status__in=["approved", "paid"])),
            )
            .filter(referral_count__gt=0)
            .order_by("-referral_count")[:10]
        )

        context["top_referrers"] = top_referrers
        logger.debug(f"[ADMIN_DASHBOARD] Loaded top {top_referrers.count()} referrers")

        # Recent activity
        context["recent_referrals"] = (
            Referral.objects.select_related("referrer", "referred")
            .order_by("-created_at")[:10]
        )
        context["recent_earnings"] = (
            ReferralEarning.objects.select_related("referrer", "referral")
            .order_by("-created_at")[:10]
        )
        
        return context


class AdminEarningsManagementView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """Admin view for managing referral earnings."""
    model = ReferralEarning
    template_name = "referrals/admin_earnings.html"
    context_object_name = "earnings"
    paginate_by = 50

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_queryset(self):
        logger.info(f"[ADMIN_EARNINGS] Loading earnings management for: {self.request.user.username}")
        
        qs = (
            ReferralEarning.objects
            .select_related("referrer", "referral", "referred_user")
            .order_by("-created_at")
        )
        
        status = self.request.GET.get("status")
        earning_type = self.request.GET.get("earning_type")
        
        if status:
            qs = qs.filter(status=status)
            logger.debug(f"[ADMIN_EARNINGS] Filtered by status: {status}")
        
        if earning_type:
            qs = qs.filter(earning_type=earning_type)
            logger.debug(f"[ADMIN_EARNINGS] Filtered by earning_type: {earning_type}")
        
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_filter"] = self.request.GET.get("status", "")
        context["earning_type_filter"] = self.request.GET.get("earning_type", "")
        return context
