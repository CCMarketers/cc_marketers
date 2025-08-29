from django.utils import timezone
from .models import Referral, ReferralEarning

def credit_signup_bonus_on_subscription(user):
    """
    Credit $5 to the direct referrer when this user subscribes,
    but only the first time (no bonus on resubscriptions).
    """
    # Check if this user has already generated a signup earning before
    already_credited = ReferralEarning.objects.filter(
        referred_user=user,
        earning_type="signup"
    ).exists()

    if already_credited:
        return  # Do nothing if already credited once

    # Find direct referral (Level 1)
    referral = Referral.objects.filter(referred=user, level=1, is_active=True).first()
    if referral:
        ReferralEarning.objects.create(
            referrer=referral.referrer,
            referred_user=user,
            referral=referral,
            amount=5.00,
            earning_type="signup",
            commission_rate=0,  # flat bonus
            status="approved",
            approved_at=timezone.now()
        )
