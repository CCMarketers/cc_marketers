from decimal import Decimal
from django.utils import timezone

from .models import Referral, ReferralEarning


def credit_signup_bonus_on_subscription(user):
    """
    Credit a one-time signup bonus to the *direct* referrer
    when this user purchases their first subscription.

    This will:
    * Do nothing if a 'signup' earning already exists for this referred_user.
    * Only credit the Level 1 (direct) referrer.
    * Instantly mark the earning as approved.
    """
    if not user or not getattr(user, "pk", None):
        return  # Defensive: skip if no valid user

    # Bail quickly if user already generated a signup earning
    if ReferralEarning.objects.filter(referred_user=user, earning_type="signup").exists():
        return

    # Look up the Level 1 referral for this user
    referral = (
        Referral.objects.filter(referred=user, level=1, is_active=True)
        .select_related("referrer")
        .first()
    )
    if not referral:
        return

    try:
        ReferralEarning.objects.create(
            referrer=referral.referrer,
            referred_user=user,
            referral=referral,
            amount=Decimal("5.00"),           # flat bonus
            earning_type="signup",
            commission_rate=Decimal("0.00"),  # not percentage
            status="approved",
            approved_at=timezone.now(),
        )
    except Exception as exc:
        # You might want to log this instead of swallowing silently
        from django.core.exceptions import ImproperlyConfigured
        # e.g., logger.warning("Could not credit signup bonus: %s", exc)
        raise ImproperlyConfigured(f"Could not credit signup bonus: {exc}")
