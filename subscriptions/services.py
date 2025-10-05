# subscriptions/services.py
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from wallets.models import Wallet
from tasks.services import TaskWalletService

from .models import SubscriptionPlan, UserSubscription


class SubscriptionService:
    """Business logic for handling user subscriptions."""

    @staticmethod
    def subscribe_user(user, plan_id):
        """
        Subscribe a user to a plan by deducting from wallet balance & allocate TaskWallet funds.
        Returns a dict with {'success': bool, 'subscription' or 'error': ...}.
        """
        with transaction.atomic():
            plan = (
                SubscriptionPlan.objects.filter(id=plan_id, is_active=True)
                .select_for_update()
                .first()
            )
            if not plan:
                return {"success": False, "error": "Plan not found"}

            wallet = Wallet.objects.select_for_update().filter(user=user).first()
            if not wallet:
                return {"success": False, "error": "Wallet not found"}

            if wallet.balance < plan.price:
                return {"success": False, "error": "Insufficient wallet balance"}

            # Cancel existing active subscriptions
            UserSubscription.objects.filter(user=user, status="active").update(status="cancelled")

            # Deduct subscription price
            wallet.balance -= plan.price
            wallet.save(update_fields=["balance"])

            # Create subscription
            subscription = UserSubscription.objects.create(
                user=user,
                plan=plan,
                start_date=timezone.now(),
                expiry_date=timezone.now() + timezone.timedelta(days=plan.duration_days),
                status="active",
            )

            # Task Wallet allocation for specific plan
            if plan.name == "Business Member Plan":
                TaskWalletService.credit_wallet(
                    user=user,
                    amount=Decimal("10.00"),
                    category="subscription_allocation",
                    description=f"Monthly allocation from subscription plan {plan.name}",
                )

        return {"success": True, "subscription": subscription}

    @staticmethod
    def check_and_renew_subscriptions():
        """
        Check for expired subscriptions and renew if auto-renewal is enabled.
        """
        expired_subscriptions = UserSubscription.objects.filter(
            status="active",
            expiry_date__lte=timezone.now(),
        ).select_related("user", "plan")

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
                        subscription.expiry_date = now + timezone.timedelta(days=subscription.plan.duration_days)
                        subscription.save(update_fields=["start_date", "expiry_date"])

                        if subscription.plan.name == "Business Member Plan":
                            TaskWalletService.credit_wallet(
                                user=subscription.user,
                                amount=Decimal("10.00"),
                                category="subscription_allocation",
                                description=f"Monthly allocation from subscription plan {subscription.plan.name}",
                            )
                        renewed = True
            if not renewed:
                subscription.status = "expired"
                subscription.save(update_fields=["status"])

    @staticmethod
    def get_user_active_subscription(user):
        """
        Get user's current active subscription or None.
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
