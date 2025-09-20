# apps/referrals/signals.py
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import ReferralCode, Referral, ReferralEarning, CommissionTier

User = get_user_model()


# ----------------------------------------------------------------------
# 1. Create ReferralCode for every new user
# ----------------------------------------------------------------------
@receiver(post_save, sender=User)
def create_referral_code(sender, instance, created, **kwargs):
    """
    Automatically create a ReferralCode when a new user is created.

    This runs before handle_user_signup to ensure the code exists.
    """
    if created and not hasattr(instance, "referral_code"):
        ReferralCode.objects.create(user=instance)


# ----------------------------------------------------------------------
# 2. Handle Direct + Indirect Referrals
# ----------------------------------------------------------------------
@receiver(post_save, sender=User)
def handle_user_signup(sender, instance, created, **kwargs):
    """
    When a new user signs up with a referral code:

    * Create Level 1 referral
    * Propagate Level 2 & Level 3 referrals automatically
    * Do NOT credit earnings here (earnings are credited later by action)
    """
    if not created:
        return

    # You can set instance.used_referral_code_id before saving the user in the view/form
    referral_code_id = getattr(instance, "used_referral_code_id", None)
    if not referral_code_id:
        return

    try:
        referral_code = ReferralCode.objects.get(id=referral_code_id, is_active=True)
    except ReferralCode.DoesNotExist:
        return

    referrer = referral_code.user

    # Level 1 (direct)
    Referral.objects.get_or_create(
        referrer=referrer,
        referred=instance,
        level=1,
        referral_code=referral_code,
    )

    # Level 2
    parent_referral = Referral.objects.filter(referred=referrer, level=1).first()
    if parent_referral:
        Referral.objects.get_or_create(
            referrer=parent_referral.referrer,
            referred=instance,
            level=2,
            referral_code=parent_referral.referral_code,
        )

        # Level 3
        grandparent_referral = Referral.objects.filter(
            referred=parent_referral.referrer, level=1
        ).first()
        if grandparent_referral:
            Referral.objects.get_or_create(
                referrer=grandparent_referral.referrer,
                referred=instance,
                level=3,
                referral_code=grandparent_referral.referral_code,
            )


# ----------------------------------------------------------------------
# 3. Helper for creating signup earnings
# ----------------------------------------------------------------------
def _create_signup_earning(referral):
    """
    Create earning for signup event.

    * Direct referrer (Level 1) always gets flat $5
    * Levels 2 and 3 can still use CommissionTier if configured
    """
    if referral.level == 1:
        ReferralEarning.objects.create(
            referrer=referral.referrer,
            referred_user=referral.referred,
            referral=referral,
            amount=Decimal("5.00"),
            earning_type="signup",
            commission_rate=Decimal("0.00"),  # Not a percentage, just flat reward
            status="approved",
            approved_at=timezone.now(),
        )
        return

    # Levels 2 and 3: use CommissionTier
    commission = CommissionTier.objects.filter(
        level=referral.level, earning_type="signup", is_active=True
    ).first()
    if commission:
        ReferralEarning.objects.create(
            referrer=referral.referrer,
            referred_user=referral.referred,
            referral=referral,
            amount=commission.rate,  # treat rate as flat amount for signup
            earning_type="signup",
            commission_rate=commission.rate,
            status="approved",
            approved_at=timezone.now(),
        )


# ----------------------------------------------------------------------
# 4. Generic earning function for tasks/funding/subscription
# ----------------------------------------------------------------------
def create_referral_earning(user, earning_type, base_amount):
    """
    Call this whenever a user performs an action (task, funding, subscription).
    It creates earnings for ALL their referrers up to Level 3.

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
