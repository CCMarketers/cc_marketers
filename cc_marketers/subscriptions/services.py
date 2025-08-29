
# subscriptions/services.py
from django.utils import timezone
from django.db import transaction
from wallets.models import Wallet  # Assuming you have this model
from .models import SubscriptionPlan, UserSubscription
from decimal import Decimal
from tasks.services import TaskWalletService

class SubscriptionService:
    
    @staticmethod
    def subscribe_user(user, plan_id):
        """Subscribe a user to a plan by deducting from wallet balance & allocate TaskWallet funds"""
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return {'success': False, 'error': 'Plan not found'}
        
        try:
            wallet = Wallet.objects.get(user=user)
        except Wallet.DoesNotExist:
            return {'success': False, 'error': 'Wallet not found'}
        
        if wallet.balance < plan.price:
            return {'success': False, 'error': 'Insufficient wallet balance'}
        
        with transaction.atomic():
            # Cancel any existing active subscriptions
            UserSubscription.objects.filter(
                user=user, 
                status='active'
            ).update(status='cancelled')
            
            # Deduct subscription price from Main Wallet
            wallet.balance -= plan.price
            wallet.save()
            
            # Create new subscription
            subscription = UserSubscription.objects.create(
                user=user,
                plan=plan,
                expiry_date=timezone.now() + timezone.timedelta(days=plan.duration_days)
            )

          
            if plan.name == "Business Member Plan":  # ✅ Allocate $10 into Task Wallet
                TaskWalletService.credit_wallet(
                    user=user,
                    amount=Decimal("10.00"),
                    category="subscription_allocation",
                    description=f"Monthly allocation from subscription plan {plan.name}"
                )

            return {'success': True, 'subscription': subscription}

    @staticmethod
    def check_and_renew_subscriptions():
        """Check for expired subscriptions and renew if auto-renewal is enabled"""
        expired_subscriptions = UserSubscription.objects.filter(
            status='active',
            expiry_date__lte=timezone.now()
        )
        
        for subscription in expired_subscriptions:
            if subscription.auto_renewal:
                try:
                    wallet = Wallet.objects.get(user=subscription.user)
                    if wallet.balance >= subscription.plan.price:
                        with transaction.atomic():
                            # Deduct renewal fee
                            wallet.balance -= subscription.plan.price
                            wallet.save()

                            # Renew subscription
                            subscription.start_date = timezone.now()
                            subscription.expiry_date = timezone.now() + timezone.timedelta(
                                days=subscription.plan.duration_days
                            )
                            subscription.save()

                            # ✅ Allocate Task Wallet funds again on renewal
                            if subscription.plan.name == "Business Member Plan":
                                TaskWalletService.credit_wallet(
                                    user=subscription.user,
                                    amount=Decimal("10.00"),
                                    category="subscription_allocation",
                                    description=f"Monthly allocation from subscription plan {subscription.plan.name}"
                                )
                            continue
                except Wallet.DoesNotExist:
                    pass
            
            # Mark as expired if not renewed
            subscription.status = 'expired'
            subscription.save()

    @staticmethod
    def get_user_active_subscription(user):
        """Get user's current active subscription"""
        try:
            return UserSubscription.objects.get(
                user=user,
                status='active',
                expiry_date__gt=timezone.now()
            )
        except UserSubscription.DoesNotExist:
            return None
