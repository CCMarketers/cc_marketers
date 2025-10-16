# apps/referrals/services.py
import logging
from decimal import Decimal
from django.utils import timezone
from .models import Referral, ReferralEarning
from subscriptions.services import SubscriptionService

logger = logging.getLogger(__name__)


def credit_signup_bonus_on_subscription(user):
    """
    Credit signup bonus for BOTH Level 1 and Level 2 referrals.
    
    Credit signup bonus ONLY if:
    1. Referrer has Business Member subscription
    2. If referrer is Demo, only credit if referred subscribes to Business Member
    """

    if not user or not getattr(user, "pk", None):
        logger.warning("Invalid user passed to credit_signup_bonus_on_subscription")
        return

    logger.info(f"Starting referral bonus processing for user: {user.username} (ID: {user.id})")

    # Prevent duplicate bonuses - check if ANY signup earning exists for this user
    if ReferralEarning.objects.filter(referred_user=user, earning_type="signup").exists():
        logger.info(f"User {user.username} already has signup earnings, skipping...")
        return

    # Get ALL referrals for this user (both Level 1 and Level 2)
    referrals = Referral.objects.filter(referred=user, is_active=True).select_related("referrer")
    
    if not referrals.exists():
        logger.info(f"No active referrals found for user {user.username}")
        return

    logger.info(f"Found {referrals.count()} referral(s) for user {user.username}")

    # New user must be a Business Member
    user_subscription = SubscriptionService.get_user_active_subscription(user)
    if not user_subscription or user_subscription.plan.name != "Business Member Account":
        logger.info(f"User {user.username} does not have Business Member subscription, cannot credit referrers")
        return

    logger.info(f"User {user.username} has Business Member subscription, processing referrers...")

    # Credit each referrer at their level
    for referral in referrals:
        referrer = referral.referrer
        
        # Referrer must be a Business Member
        referrer_subscription = SubscriptionService.get_user_active_subscription(referrer)
        if not referrer_subscription or referrer_subscription.plan.name != "Business Member Account":
            logger.info(f"Referrer {referrer.username} does not have Business Member subscription (Level {referral.level}), skipping...")
            continue
        
        # Determine bonus amount based on level
        if referral.level == 1:
            amount = Decimal("5.00")
        elif referral.level == 2:
            amount = Decimal("3.00")
        else:
            # Level 3 or higher - use CommissionTier if available
            logger.info(f"Referral level {referral.level} not supported for flat bonus")
            continue
        
        # Create the earning
        try:
            ReferralEarning.objects.create(
                referrer=referrer,
                referred_user=user,
                referral=referral,
                amount=amount,
                earning_type="signup",
                commission_rate=Decimal("0.00"),
                status="approved",
                approved_at=timezone.now(),
            )
            logger.info(f"✅ {referrer.username} credited ₦{amount} for referring {user.username} (Level {referral.level})")
        except Exception as exc:
            logger.error(f"Failed to credit {referrer.username}: {exc}")
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured(f"Could not credit signup bonus: {exc}")