# referrals/views.py
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Count
from django.urls import reverse
from django.views.generic import ListView, TemplateView

from .models import Referral, ReferralEarning, ReferralCode, CommissionTier

User = get_user_model()


class ReferralDashboardView(LoginRequiredMixin, TemplateView):
    """User dashboard for viewing referral stats."""
    template_name = "referrals/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Always get or create a referral code for the user
        referral_code, _ = ReferralCode.objects.get_or_create(
            user=user, defaults={"is_active": True}
        )

        # Pre-calculate stats with aggregation to avoid N+1
        approved_qs = ReferralEarning.objects.filter(
            referrer=user, status__in=["approved", "paid"]
        )
        pending_qs = ReferralEarning.objects.filter(referrer=user, status="pending")

        context.update(
            {
                "referral_code": referral_code,
                "referral_link": self.request.build_absolute_uri(
                    reverse("users:register") + f"?ref={referral_code.code}"
                ),
                "total_referrals": Referral.objects.filter(referrer=user).count(),
                "total_earnings": approved_qs.aggregate(total=Sum("amount"))["total"] or 0,
                "pending_earnings": pending_qs.aggregate(total=Sum("amount"))["total"] or 0,
                "recent_referrals": Referral.objects.filter(referrer=user)
                .select_related("referred")
                .order_by("-created_at")[:5],
                "recent_earnings": ReferralEarning.objects.filter(referrer=user)
                .select_related("referral")
                .order_by("-created_at")[:5],
            }
        )
        return context


class ReferralListView(LoginRequiredMixin, ListView):
    """List of all referrals made by the current user."""
    model = Referral
    template_name = "referrals/referral_list.html"
    context_object_name = "referrals"
    paginate_by = 20

    def get_queryset(self):
        return (
            Referral.objects.filter(referrer=self.request.user)
            .select_related("referred")
            .order_by("-created_at")
        )


class EarningsListView(LoginRequiredMixin, ListView):
    """List of all referral earnings for the current user."""
    model = ReferralEarning
    template_name = "referrals/earnings_list.html"
    context_object_name = "earnings"
    paginate_by = 20

    def get_queryset(self):
        return (
            ReferralEarning.objects.filter(referrer=self.request.user)
            .select_related("referral")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        # Summaries in one place to avoid repeating queries
        earnings_qs = ReferralEarning.objects.filter(referrer=user)
        context["earnings_summary"] = {
            "total": earnings_qs.filter(status__in=["approved", "paid"])
            .aggregate(total=Sum("amount"))["total"]
            or 0,
            "pending": earnings_qs.filter(status="pending").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0,
            "paid": earnings_qs.filter(status="paid").aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0,
        }
        return context


class CommissionTiersView(TemplateView):
    """Public view showing commission tiers."""
    template_name = "referrals/commission_tiers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tiers = CommissionTier.objects.filter(is_active=True).order_by("level", "earning_type")

        for tier in tiers:
            if tier.earning_type == "task_completion":
                tier.display_rate = f"${tier.rate * Decimal('0.50'):.2f} per $50 task"
            elif tier.earning_type == "advertiser_funding":
                tier.display_rate = f"${tier.rate:.0f} per $1000 funding"
            elif tier.earning_type == "signup":
                tier.display_rate = f"${tier.rate * Decimal('0.10'):.2f} per signup"
            else:
                tier.display_rate = "Varies by amount"

        context["commission_tiers"] = tiers
        return context


# Admin views
class AdminReferralDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Admin dashboard for overview of all referral stats."""
    template_name = "referrals/admin_dashboard.html"

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Global stats
        context["total_users"] = User.objects.count()
        context["total_referrals"] = Referral.objects.count()
        context["total_earnings"] = ReferralEarning.objects.aggregate(total=Sum("amount"))[
            "total"
        ] or 0
        context["pending_earnings"] = ReferralEarning.objects.filter(status="pending").aggregate(
            total=Sum("amount")
        )["total"] or 0

        # Top referrers – annotate once
        top_referrers = (
            User.objects.annotate(
                referral_count=Count("referrals_made", distinct=True),
                total_earned=Sum("referral_earnings__amount"),
            )
            .filter(referral_count__gt=0)
            .order_by("-referral_count")[:10]
        )

        context["top_referrers"] = top_referrers

        # Recent activity with select_related to avoid N+1
        context["recent_referrals"] = Referral.objects.select_related("referrer", "referred").order_by(
            "-created_at"
        )[:10]
        context["recent_earnings"] = ReferralEarning.objects.select_related("referrer", "referral").order_by(
            "-created_at"
        )[:10]
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
        qs = ReferralEarning.objects.select_related("referrer", "referral").order_by("-created_at")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_filter"] = self.request.GET.get("status", "")
        return context
