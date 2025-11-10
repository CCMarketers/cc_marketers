# subscriptions/services.py
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from wallets.models import Wallet
from tasks.services import TaskWalletService
from referrals.services import (
    ReferralEarningService, 
    ReferralSubscriptionHandler
)

from .models import SubscriptionPlan, UserSubscription

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Business logic for handling user subscriptions."""

    @staticmethod
    def subscribe_user(user, plan_id):
        """
        Subscribe a user to a plan by deducting from wallet balance & allocate TaskWallet funds.
        ✅ NOW HANDLES: Demo → Cancel → Business scenario
        """
        logger.info(f"[SUBSCRIPTION] User {user.username} attempting to subscribe to plan {plan_id}")
        
        with transaction.atomic():
            plan = (
                SubscriptionPlan.objects.filter(id=plan_id, is_active=True)
                .select_for_update()
                .first()
            )
            if not plan:
                logger.warning(f"[SUBSCRIPTION] Plan {plan_id} not found")
                return {"success": False, "error": "Plan not found"}

            wallet = Wallet.objects.select_for_update().filter(user=user).first()
            if not wallet:
                logger.warning(f"[SUBSCRIPTION] Wallet not found for {user.username}")
                return {"success": False, "error": "Wallet not found"}

            if wallet.balance < plan.price:
                logger.warning(
                    f"[SUBSCRIPTION] Insufficient balance for {user.username}: "
                    f"₦{wallet.balance} < ₦{plan.price}"
                )
                return {"success": False, "error": "Insufficient wallet balance"}

            # ✅ FIX: Get OLD subscription (including cancelled ones for tracking)
            old_subscription = UserSubscription.objects.filter(
                user=user,
                status__in=["active", "cancelled", "expired"]  # ← Include cancelled!
            ).order_by("-created_at").first()
            
            old_plan_name = old_subscription.plan.name if old_subscription else None
            
            # ✅ FIX: Check if user ever had a Business subscription before
            had_business_before = UserSubscription.objects.filter(
                user=user,
                plan__name="Business Member Account",
                status__in=["active", "cancelled", "expired"]
            ).exists()
            
            logger.info(
                f"[SUBSCRIPTION] {user.username} changing from "
                f"'{old_plan_name or 'None'}' to '{plan.name}' "
                f"(had_business_before: {had_business_before})"
            )

            # Cancel existing active subscriptions
            UserSubscription.objects.filter(user=user, status="active").update(status="cancelled")

            # Deduct subscription price
            wallet.balance -= plan.price
            wallet.save(update_fields=["balance"])
            
            logger.info(f"[SUBSCRIPTION] Deducted ₦{plan.price} from {user.username}'s wallet")

            # Create subscription
            subscription = UserSubscription.objects.create(
                user=user,
                plan=plan,
                start_date=timezone.now(),
                expiry_date=timezone.now() + timezone.timedelta(days=plan.duration_days),
                status="active",
            )
            
            logger.info(
                f"[SUBSCRIPTION] ✅ Created subscription {subscription.id} for {user.username} "
                f"(expires: {subscription.expiry_date})"
            )

            # Task Wallet allocation for Business Member
            if subscription.plan.name.strip().lower() == "business member account":
                TaskWalletService.credit_wallet(
                    user=user,
                    amount=Decimal("10000.00"),
                    category="subscription_allocation",
                    description=f"Monthly allocation from subscription plan {plan.name}",
                )
                logger.info(f"[SUBSCRIPTION] Credited ₦10,000 task wallet for {user.username}")

            # ✅ NEW: Handle all subscription state changes
            new_plan_name = plan.name
            
            # Case 1: Demo → Business (upgrade)
            if old_plan_name == "Demo Account" and new_plan_name == "Business Member Account":
                logger.info(f"[SUBSCRIPTION] Processing UPGRADE: Demo → Business")
                ReferralSubscriptionHandler.handle_subscription_upgrade(
                    user, old_plan_name, new_plan_name
                )
                # Credit signup bonuses
                ReferralEarningService.credit_signup_bonus(user)
            
            # Case 2: Business → Demo (downgrade)
            elif old_plan_name == "Business Member Account" and new_plan_name == "Demo Account":
                logger.warning(f"[SUBSCRIPTION] Processing DOWNGRADE: Business → Demo")
                ReferralSubscriptionHandler.handle_subscription_downgrade(
                    user, old_plan_name, new_plan_name
                )
            
            # ✅ Case 3: No previous subscription OR resubscribing after cancellation
            elif not old_plan_name or old_subscription.status in ["cancelled", "expired"]:
                if new_plan_name == "Business Member Account":
                    logger.info(
                        f"[SUBSCRIPTION] New or resubscribed Business Member - "
                        f"enabling referral privileges"
                    )
                    # Re-enable referral privileges
                    ReferralSubscriptionHandler.reactivate_referral_code(user)
                    
                    # Credit signup bonuses ONLY if never had Business before
                    if not had_business_before:
                        logger.info(f"[SUBSCRIPTION] First-time Business signup, crediting bonuses")
                        ReferralEarningService.credit_signup_bonus(user)
                    else:
                        logger.info(f"[SUBSCRIPTION] Returning Business member, no new bonuses")
                
                elif new_plan_name == "Demo Account":
                    logger.info(f"[SUBSCRIPTION] Demo subscription - limited referral privileges")
                    # Enable referral code but with Demo restrictions
                    ReferralSubscriptionHandler.reactivate_referral_code(user)
            
            # Case 4: Business → Business (renewal/resubscribe)
            elif old_plan_name == "Business Member Account" and new_plan_name == "Business Member Account":
                logger.info(f"[SUBSCRIPTION] Business renewal, no bonus crediting")
            
            logger.info(f"[SUBSCRIPTION] 🎉 Subscription complete for {user.username}")

        return {"success": True, "subscription": subscription}


    @staticmethod
    def check_and_renew_subscriptions():
        """
        Check for expired subscriptions and renew if auto-renewal is enabled.
        ✅ NO CHANGES NEEDED HERE - renewals don't trigger new referral bonuses
        """
        logger.info("[SUBSCRIPTION_RENEWAL] Checking for expired subscriptions...")
        
        expired_subscriptions = UserSubscription.objects.filter(
            status="active",
            expiry_date__lte=timezone.now(),
        ).select_related("user", "plan")
        
        logger.info(f"[SUBSCRIPTION_RENEWAL] Found {expired_subscriptions.count()} expired subscriptions")

        for subscription in expired_subscriptions:
            renewed = False
            if getattr(subscription, "auto_renewal", False):
                wallet = Wallet.objects.select_for_update().filter(user=subscription.user).first()
                if wallet and wallet.balance >= subscription.plan.price:
                    with transaction.atomic():
                        # Deduct renewal fee
                        wallet.balance -= subscription.plan.price
                        wallet.save(update_fields=["balance"])

                        # Renew subscription
                        now = timezone.now()
                        subscription.start_date = now
                        subscription.expiry_date = now + timezone.timedelta(
                            days=subscription.plan.duration_days
                        )
                        subscription.save(update_fields=["start_date", "expiry_date"])
                        
                        if subscription.plan.name.strip().lower() == "business member account":
                            TaskWalletService.credit_wallet(
                                user=subscription.user,
                                amount=Decimal("10000.00"),
                                category="subscription_allocation",
                                description=f"Monthly allocation from renewed plan {subscription.plan.name}",
                            )
                        
                        renewed = True
                        logger.info(
                            f"[SUBSCRIPTION_RENEWAL] ✅ Renewed subscription for "
                            f"{subscription.user.username}"
                        )
            
            if not renewed:
                subscription.status = "expired"
                subscription.save(update_fields=["status"])
                logger.info(
                    f"[SUBSCRIPTION_RENEWAL] Expired subscription for "
                    f"{subscription.user.username} (not renewed)"
                )

    @staticmethod
    def get_user_active_subscription(user):
        """
        Get user's current active subscription or None.
        ✅ NO CHANGES NEEDED
        """
        return (
            UserSubscription.objects.filter(
                user=user,
                status="active",
                expiry_date__gt=timezone.now(),
            )
            .order_by("-expiry_date")
            .first()
        )