# tests/test_services.py
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from subscriptions.services import SubscriptionService
from subscriptions.models import UserSubscription
from .test_base import BaseTestMixin, BaseTransactionTestCase



class SubscriptionServiceTest(BaseTransactionTestCase, BaseTestMixin):
    """Test SubscriptionService"""

    def test_subscribe_user_success(self):
        """Test successful user subscription"""
        initial_balance = self.wallet.balance
        
        result = SubscriptionService.subscribe_user(self.user, self.basic_plan.id)
        
        self.assertTrue(result['success'])
        self.assertIn('subscription', result)
        
        # Check wallet balance deducted
        self.wallet.refresh_from_db()
        expected_balance = initial_balance - self.basic_plan.price
        self.assertDecimalEqual(self.wallet.balance, expected_balance)
        
        # Check subscription created
        subscription = result['subscription']
        self.assertEqual(subscription.user, self.user)
        self.assertEqual(subscription.plan, self.basic_plan)
        self.assertEqual(subscription.status, 'active')

    def test_subscribe_user_plan_not_found(self):
        """Test subscription with non-existent plan"""
        result = SubscriptionService.subscribe_user(self.user, 99999)
        
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Plan not found')

    def test_subscribe_user_inactive_plan(self):
        """Test subscription with inactive plan"""
        inactive_plan = self.create_subscription_plan(
            name='Inactive Plan',
            is_active=False
        )
        
        result = SubscriptionService.subscribe_user(self.user, inactive_plan.id)
        
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Plan not found')

    def test_subscribe_user_wallet_not_found(self):
        """Test subscription when user has no wallet"""
        # Delete user's wallet
        self.wallet.delete()
        
        result = SubscriptionService.subscribe_user(self.user, self.basic_plan.id)
        
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Wallet not found')

    def test_subscribe_user_insufficient_balance(self):
        """Test subscription with insufficient wallet balance"""
        # Set balance lower than plan price
        self.wallet.balance = Decimal('2.00')
        self.wallet.save()
        
        result = SubscriptionService.subscribe_user(self.user, self.basic_plan.id)
        
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Insufficient wallet balance')

    def test_subscribe_user_cancels_existing_subscription(self):
        """Test new subscription cancels existing active subscription"""
        # Create existing active subscription
        existing_sub = self.create_subscription()
        
        result = SubscriptionService.subscribe_user(self.user, self.premium_plan.id)
        
        self.assertTrue(result['success'])
        
        # Check existing subscription was cancelled
        existing_sub.refresh_from_db()
        self.assertEqual(existing_sub.status, 'cancelled')
        
        # Check new subscription is active
        new_sub = result['subscription']
        self.assertEqual(new_sub.status, 'active')
        self.assertEqual(new_sub.plan, self.premium_plan)

    @patch('tasks.services.TaskWalletService.credit_wallet')
    def test_subscribe_user_business_plan_task_wallet_allocation(self, mock_credit):
        """Test business plan subscription allocates task wallet funds"""
        mock_credit.return_value = MagicMock()
        
        result = SubscriptionService.subscribe_user(self.user, self.business_plan.id)
        
        self.assertTrue(result['success'])
        
        # Check task wallet credit was called
        mock_credit.assert_called_once_with(
            user=self.user,
            amount=Decimal("10.00"),
            category="subscription_allocation",
            description=f"Monthly allocation from subscription plan {self.business_plan.name}"
        )

    @patch('tasks.services.TaskWalletService.credit_wallet')
    def test_subscribe_user_non_business_plan_no_allocation(self, mock_credit):
        """Test non-business plan subscription doesn't allocate task wallet funds"""
        result = SubscriptionService.subscribe_user(self.user, self.basic_plan.id)
        
        self.assertTrue(result['success'])
        
        # Check task wallet credit was NOT called
        mock_credit.assert_not_called()

    def test_get_user_active_subscription_found(self):
        """Test getting user's active subscription"""
        subscription = self.create_subscription()
        
        active_sub = SubscriptionService.get_user_active_subscription(self.user)
        
        self.assertEqual(active_sub, subscription)

    def test_get_user_active_subscription_not_found(self):
        """Test getting user's active subscription when none exists"""
        active_sub = SubscriptionService.get_user_active_subscription(self.user)
        
        self.assertIsNone(active_sub)

    def test_get_user_active_subscription_expired(self):
        """Test getting active subscription ignores expired ones"""
        # Create expired subscription
        past_date = timezone.now() - timedelta(days=1)
        self.create_subscription(expiry_date=past_date)
        
        active_sub = SubscriptionService.get_user_active_subscription(self.user)
        
        self.assertIsNone(active_sub)

    def test_get_user_active_subscription_cancelled(self):
        """Test getting active subscription ignores cancelled ones"""
        self.create_subscription(status='cancelled')
        
        active_sub = SubscriptionService.get_user_active_subscription(self.user)
        
        self.assertIsNone(active_sub)

    def test_check_and_renew_subscriptions_success(self):
        """Test successful subscription renewal"""
        # Create expired subscription with auto-renewal
        past_date = timezone.now() - timedelta(hours=1)
        subscription = self.create_subscription(
            expiry_date=past_date,
            auto_renewal=True
        )
        initial_balance = self.wallet.balance
        
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check subscription was renewed
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'active')
        self.assertGreater(subscription.expiry_date, timezone.now())
        
        # Check wallet balance was deducted
        self.wallet.refresh_from_db()
        expected_balance = initial_balance - subscription.plan.price
        self.assertDecimalEqual(self.wallet.balance, expected_balance)

    def test_check_and_renew_subscriptions_insufficient_balance(self):
        """Test subscription renewal with insufficient balance"""
        # Set wallet balance to insufficient amount
        self.wallet.balance = Decimal('1.00')
        self.wallet.save()
        
        # Create expired subscription with auto-renewal
        past_date = timezone.now() - timedelta(hours=1)
        subscription = self.create_subscription(
            expiry_date=past_date,
            auto_renewal=True
        )
        
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check subscription was marked as expired
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'expired')

    def test_check_and_renew_subscriptions_no_wallet(self):
        """Test subscription renewal when user has no wallet"""
        # Delete user's wallet
        self.wallet.delete()
        
        # Create expired subscription with auto-renewal
        past_date = timezone.now() - timedelta(hours=1)
        subscription = self.create_subscription(
            expiry_date=past_date,
            auto_renewal=True
        )
        
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check subscription was marked as expired
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'expired')

    def test_check_and_renew_subscriptions_auto_renewal_disabled(self):
        """Test subscription not renewed when auto-renewal is disabled"""
        # Create expired subscription without auto-renewal
        past_date = timezone.now() - timedelta(hours=1)
        subscription = self.create_subscription(
            expiry_date=past_date,
            auto_renewal=False
        )
        
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check subscription was marked as expired
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'expired')

    @patch('tasks.services.TaskWalletService.credit_wallet')
    def test_check_and_renew_business_plan_allocates_funds(self, mock_credit):
        """Test business plan renewal allocates task wallet funds"""
        mock_credit.return_value = MagicMock()
        
        # Create expired business plan subscription
        past_date = timezone.now() - timedelta(hours=1)
        self.create_subscription(
            plan=self.business_plan,
            expiry_date=past_date,
            auto_renewal=True
        )
        
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check task wallet credit was called
        mock_credit.assert_called_once_with(
            user=self.user,
            amount=Decimal("10.00"),
            category="subscription_allocation",
            description=f"Monthly allocation from subscription plan {self.business_plan.name}"
        )

    def test_check_and_renew_subscriptions_multiple_users(self):
        """Test renewal process handles multiple users"""
        # Create expired subscriptions for multiple users
        past_date = timezone.now() - timedelta(hours=1)
        
        sub1 = self.create_subscription(
            user=self.user,
            expiry_date=past_date,
            auto_renewal=True
        )
        
        sub2 = self.create_subscription(
            user=self.user2,
            expiry_date=past_date,
            auto_renewal=True
        )
        
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check both subscriptions were renewed
        sub1.refresh_from_db()
        sub2.refresh_from_db()
        
        self.assertEqual(sub1.status, 'active')
        self.assertEqual(sub2.status, 'active')

    def test_check_and_renew_subscriptions_no_expired(self):
        """Test renewal process when no subscriptions are expired"""
        # Create active subscription
        future_date = timezone.now() + timedelta(days=10)
        subscription = self.create_subscription(
            expiry_date=future_date,
            auto_renewal=True
        )
        
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check subscription remains active and unchanged
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'active')
        self.assertEqual(subscription.expiry_date, future_date)

    def test_atomic_transaction_rollback_on_error(self):
        """Test that subscription creation is atomic"""
        original_balance = self.wallet.balance
        
        # Mock TaskWalletService to raise an exception for business plan
        with patch('tasks.services.TaskWalletService.credit_wallet') as mock_credit:
            mock_credit.side_effect = Exception("Task wallet error")
            
            result = SubscriptionService.subscribe_user(self.user, self.business_plan.id)
            
            # Should fail due to exception
            self.assertFalse(result['success'])
            
            # Wallet balance should remain unchanged due to transaction rollback
            self.wallet.refresh_from_db()
            self.assertDecimalEqual(self.wallet.balance, original_balance)
            
            # No subscription should be created
            self.assertFalse(
                UserSubscription.objects.filter(
                    user=self.user,
                    plan=self.business_plan
                ).exists()
            )