# apps/referrals/utils.py
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db.models import Sum
from .models import Referral, ReferralEarning, CommissionTier, ReferralCode

User = get_user_model()


def process_referral_signup(user, referral_code):
    """Process referral when a new user signs up with a referral code"""
    try:
        ref_code = ReferralCode.objects.get(code=referral_code, is_active=True)
        referrer = ref_code.user

        # Don't allow self-referral
        if referrer == user:
            return None

        # Create direct referral (Level 1)
        referral = Referral.objects.create(
            referrer=referrer,
            referred=user,
            level=1,
            referral_code=ref_code
        )

        # Check for multi-tier referrals (up to 3 levels)
        create_multi_tier_referrals(user, referrer)

        return referral

    except ReferralCode.DoesNotExist:
        return None


def create_multi_tier_referrals(new_user, direct_referrer):
    """Create multi-tier referrals up to 3 levels"""
    current_referrer = direct_referrer
    level = 2

    while level <= 3:
        try:
            # Find who referred the current referrer at level 1
            parent_referral = Referral.objects.get(referred=current_referrer, level=1)
            parent_referrer = parent_referral.referrer

            # Use the parent's referral_code if available
            referral_code = ReferralCode.objects.filter(user=parent_referrer, is_active=True).first()

            Referral.objects.create(
                referrer=parent_referrer,
                referred=new_user,
                level=level,
                referral_code=referral_code
            )

            current_referrer = parent_referrer
            level += 1

        except Referral.DoesNotExist:
            break


def calculate_referral_commission(referred_user, earning_type, base_amount):
    """Calculate and create referral earnings for all levels"""
    referrals = Referral.objects.filter(referred=referred_user, is_active=True)

    for referral in referrals:
        try:
            commission_tier = CommissionTier.objects.get(
                level=referral.level,
                earning_type=earning_type,
                is_active=True
            )

            commission_amount = base_amount * (commission_tier.rate / Decimal('100'))

            ReferralEarning.objects.create(
                referrer=referral.referrer,
                referred_user=referred_user,
                referral=referral,
                amount=commission_amount,
                earning_type=earning_type,
                commission_rate=commission_tier.rate,
                status='pending'
            )

        except CommissionTier.DoesNotExist:
            continue


def get_referral_stats(user):
    """Get comprehensive referral statistics for a user"""
    referrals = Referral.objects.filter(referrer=user)
    earnings = ReferralEarning.objects.filter(referrer=user)

    return {
        'total_referrals': referrals.count(),
        'direct_referrals': referrals.filter(level=1).count(),
        'indirect_referrals': referrals.filter(level__gt=1).count(),
        'total_earnings': earnings.filter(status__in=['approved', 'paid']).aggregate(
            Sum('amount'))['amount__sum'] or Decimal('0'),
        'pending_earnings': earnings.filter(status='pending').aggregate(
            Sum('amount'))['amount__sum'] or Decimal('0'),
        'paid_earnings': earnings.filter(status='paid').aggregate(
            Sum('amount'))['amount__sum'] or Decimal('0'),
    }
