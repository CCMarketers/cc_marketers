from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Referral, ReferralCode, ReferralEarning, CommissionTier
# from .services import credit_signup_bonus_on_subscription
User = get_user_model()


# 1. Create ReferralCode for every new user
@receiver(post_save, sender=User)
def create_referral_code(sender, instance, created, **kwargs):
    """
    Automatically create a ReferralCode when a new user is created.

    This runs before handle_user_signup to ensure the code exists.
    """
    if created and not hasattr(instance, "referral_code"):
        ReferralCode.objects.create(user=instance)


# 2. Handle Direct + Indirect Referrals
@receiver(post_save, sender=User)
def handle_user_signup(sender, instance, created, **kwargs):
    """
    Handles referral signup:
    - Level 1 (direct referrer): gets $5
    - Level 2 (referrer's referrer): gets $3
    """
    if not created:
        return

    referral_code_id = getattr(instance, "used_referral_code_id", None)
    if not referral_code_id:
        return

    try:
        referral_code = ReferralCode.objects.get(id=referral_code_id, is_active=True)
    except ReferralCode.DoesNotExist:
        return

    referrer = referral_code.user

    # -------- LEVEL 1 REFERRAL (Direct: referrer gets $5) --------
    referral_lvl1, _ = Referral.objects.get_or_create(
        referrer=referrer,
        referred=instance,
        level=1,
        referral_code=referral_code,
    )
    _create_signup_earning(referral_lvl1)

    # -------- LEVEL 2 REFERRAL (Indirect: referrer's referrer gets $3) --------
    # Find the person who referred the direct referrer
    parent_referral = Referral.objects.filter(referred=referrer, level=1).first()
    if parent_referral:
        referral_lvl2, _ = Referral.objects.get_or_create(
            referrer=parent_referral.referrer,
            referred=instance,
            level=2,
            referral_code=parent_referral.referral_code,
        )
        _create_signup_earning(referral_lvl2)


# 3. Helper for creating signup earnings
def _create_signup_earning(referral):
    """
    Create earning for signup event based on referral level.

    * Level 1 (direct referrer): gets $5
    * Level 2 (indirect referrer): gets $3
    """
    if referral.level == 1:
        amount = Decimal("5.00")
    elif referral.level == 2:
        amount = Decimal("3.00")
    else:
        return  # No earnings for levels beyond 2

    ReferralEarning.objects.create(
        referrer=referral.referrer,
        referred_user=referral.referred,
        referral=referral,
        amount=amount,
        earning_type="signup",
        commission_rate=Decimal("0.00"),
        status="approved",
        approved_at=timezone.now(),
    )


# 4. Generic earning function for tasks/funding/subscription
def create_referral_earning(user, earning_type, base_amount):
    """
    Call this whenever a user performs an action (task, funding, subscription).
    It creates earnings for ALL their referrers up to Level 2.

    :param user: the user who performed the action
    :param earning_type: str, one of ReferralEarning.EARNING_TYPES
    :param base_amount: Decimal or float, the base amount to compute commission on
    """
    if not base_amount or base_amount <= 0:
        return

    base_amount = Decimal(base_amount)

    referrals = Referral.objects.filter(referred=user, is_active=True)

    for referral in referrals:
        commission = CommissionTier.objects.filter(
            level=referral.level, earning_type=earning_type, is_active=True
        ).first()
        if not commission:
            continue

        earning_amount = (commission.rate / Decimal("100")) * base_amount
        ReferralEarning.objects.create(
            referrer=referral.referrer,
            referred_user=user,
            referral=referral,
            amount=earning_amount,
            earning_type=earning_type,
            commission_rate=commission.rate,
            status="pending",
        )