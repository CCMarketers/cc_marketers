from decimal import Decimal
from django.utils import timezone
from .models import Referral, ReferralEarning
from subscriptions.services import SubscriptionService


def credit_signup_bonus_on_subscription(user):
    """
    Credit signup bonus ONLY if:
    1. Referrer has Business Member subscription
    2. If referrer is Demo, only credit if referred subscribes to Business Member
    """

    if not user or not getattr(user, "pk", None):
        return

    # Prevent duplicate bonuses
    if ReferralEarning.objects.filter(referred_user=user, earning_type="signup").exists():
        return

    # Get the direct referrer (level 1)
    referral = Referral.objects.filter(referred=user, level=1, is_active=True).select_related("referrer").first()
    if not referral:
        return

    # Condition 1: New user must be a Business Member
    user_subscription = SubscriptionService.get_user_active_subscription(user)
    if not user_subscription or user_subscription.plan.name != "Business Member Account":
        return

    # Condition 2: Referrer must be a Business Member
    referrer = referral.referrer
    referrer_subscription = SubscriptionService.get_user_active_subscription(referrer)
    if not referrer_subscription or referrer_subscription.plan.name != "Business Member Account":
        return
    
    # Credit the bonus
    try:
        ReferralEarning.objects.create(
            referrer=referrer,
            referred_user=user,
            referral=referral,
            amount=Decimal("5.00"),  # flat bonus
            earning_type="signup",
            commission_rate=Decimal("0.00"),
            status="approved",
            approved_at=timezone.now(),
        )
    except Exception as exc:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(f"Could not credit signup bonus: {exc}")
