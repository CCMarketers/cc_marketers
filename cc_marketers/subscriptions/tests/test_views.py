# tests/test_views.py
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from subscriptions.models import  UserSubscription
from .test_base import BaseViewTestCase 

User = get_user_model()


class SubscriptionPlansViewTest(BaseViewTestCase):
    """Test subscription_plans view"""

    def test_subscription_plans_anonymous_user(self):
        """Test subscription plans view for anonymous user"""
        url = reverse('subscriptions:plans')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_plan.name)
        self.assertContains(response, self.business_plan.name)
        self.assertContains(response, self.premium_plan.name)
        
        # Check context
        self.assertEqual(len(response.context['plans']), 3)
        self.assertEqual(response.context['user_wallet_balance'], 0)
        self.assertIsNone(response.context['active_subscription'])

    def test_subscription_plans_authenticated_user(self):
        """Test subscription plans view for authenticated user"""
        self.login_user()
        url = reverse('subscriptions:plans')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_plan.name)
        
        # Check context includes user wallet balance
        self.assertDecimalEqual(
            response.context['user_wallet_balance'], 
            self.wallet.balance
        )
        self.assertIsNone(response.context['active_subscription'])

    def test_subscription_plans_user_with_active_subscription(self):
        """Test subscription plans view for user with active subscription"""
        subscription = self.create_subscription()
        self.login_user()
        
        url = reverse('subscriptions:plans')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_subscription'], subscription)

    def test_subscription_plans_user_no_wallet(self):
        """Test subscription plans view for user without wallet"""
        self.wallet.delete()
        self.login_user()
        
        url = reverse('subscriptions:plans')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['user_wallet_balance'], 0)

    def test_subscription_plans_only_active_plans(self):
        """Test view only shows active subscription plans"""
        inactive_plan = self.create_subscription_plan(
            name='Inactive Plan',
            is_active=False
        )
        
        url = reverse('subscriptions:plans')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['plans']), 3)  # Only active plans
        self.assertNotContains(response, inactive_plan.name)


class SubscribeViewTest(BaseViewTestCase):
    """Test subscribe view"""

    def test_subscribe_get_redirects_to_plans(self):
        """Test GET request to subscribe redirects to plans"""
        self.login_user()
        url = reverse('subscriptions:subscribe', args=[self.basic_plan.id])
        response = self.client.get(url)
        
        self.assertRedirects(response, reverse('subscriptions:plans'))

    def test_subscribe_anonymous_user_redirects(self):
        """Test anonymous user is redirected to login"""
        url = reverse('subscriptions:subscribe', args=[self.basic_plan.id])
        response = self.client.post(url)
        
        expected_url = f'/login/?next={url}'
        self.assertRedirects(response, expected_url)


    @patch('subscriptions.views.credit_signup_bonus_on_subscription')
    def test_subscribe_success(self, mock_bonus):
        self.login_user()
        initial_balance = self.wallet.balance
        
        url = reverse('subscriptions:subscribe', args=[self.basic_plan.id])
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Successfully subscribed', str(messages[0]))
        
        # Check subscription was created
        subscription = UserSubscription.objects.get(
            user=self.user,
            plan=self.basic_plan
        )
        self.assertEqual(subscription.status, 'active')
        
        # Check wallet balance was deducted
        self.wallet.refresh_from_db()
        expected_balance = initial_balance - self.basic_plan.price
        self.assertDecimalEqual(self.wallet.balance, expected_balance)
        
        # Check bonus was credited
        mock_bonus.assert_called_once_with(self.user)



    def test_subscribe_with_existing_active_subscription(self):
        """Test subscribe when user already has active subscription"""
        existing_sub = self.create_subscription()
        self.login_user()
        
        url = reverse('subscriptions:subscribe', args=[self.premium_plan.id])
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('already have an active subscription', str(messages[0]))
        self.assertIn(existing_sub.plan.name, str(messages[0]))

    def test_subscribe_insufficient_balance(self):
        """Test subscribe with insufficient wallet balance"""
        self.wallet.balance = Decimal('1.00')
        self.wallet.save()
        self.login_user()
        
        url = reverse('subscriptions:subscribe', args=[self.basic_plan.id])
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:plans'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Insufficient wallet balance', str(messages[0]))

    def test_subscribe_nonexistent_plan(self):
        """Test subscribe with non-existent plan"""
        self.login_user()
        
        url = reverse('subscriptions:subscribe', args=[99999])
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:plans'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Plan not found', str(messages[0]))

    def test_subscribe_no_wallet(self):
        """Test subscribe when user has no wallet"""
        self.wallet.delete()
        self.login_user()
        
        url = reverse('subscriptions:subscribe', args=[self.basic_plan.id])
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:plans'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Wallet not found', str(messages[0]))


class MySubscriptionViewTest(BaseViewTestCase):
    """Test my_subscription view"""

    def test_my_subscription_anonymous_user_redirects(self):
        """Test anonymous user is redirected to login"""
        url = reverse('subscriptions:my_subscription')
        response = self.client.get(url)
        
        expected_url = f'/login/?next={url}'
        self.assertRedirects(response, expected_url)

    def test_my_subscription_with_active_subscription(self):
        """Test my subscription view with active subscription"""
        subscription = self.create_subscription()
        self.login_user()
        
        url = reverse('subscriptions:my_subscription')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_subscription'], subscription)
        self.assertDecimalEqual(
            response.context['wallet_balance'],
            self.wallet.balance
        )
        
        # Check subscription history
        history = response.context['subscription_history']
        self.assertEqual(history.count(), 1)
        self.assertIn(subscription, history)

    def test_my_subscription_no_active_subscription(self):
        """Test my subscription view without active subscription"""
        self.login_user()
        
        url = reverse('subscriptions:my_subscription')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['active_subscription'])
        self.assertEqual(response.context['subscription_history'].count(), 0)

    def test_my_subscription_with_pending_withdrawals(self):
        """Test wallet balance calculation with pending withdrawals"""
        withdrawal = self.create_withdrawal_request(
            user=self.user,
            amount=Decimal('20.00'),
            status='pending'
        )
        self.login_user()
        
        url = reverse('subscriptions:my_subscription')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        expected_balance = self.wallet.balance - withdrawal.amount
        self.assertDecimalEqual(
            response.context['wallet_balance'],
            expected_balance
        )

    def test_my_subscription_multiple_pending_withdrawals(self):
        """Test wallet balance with multiple pending withdrawals"""
        self.create_withdrawal_request(
            user=self.user,
            amount=Decimal('10.00'),
            status='pending'
        )
        self.create_withdrawal_request(
            user=self.user,
            amount=Decimal('15.00'),
            status='pending'
        )
        # Approved withdrawal should not affect balance
        self.create_withdrawal_request(
            user=self.user,
            amount=Decimal('5.00'),
            status='approved'
        )
        
        self.login_user()
        
        url = reverse('subscriptions:my_subscription')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        expected_balance = self.wallet.balance - Decimal('25.00')  # Only pending
        self.assertDecimalEqual(
            response.context['wallet_balance'],
            expected_balance
        )

    def test_my_subscription_no_wallet(self):
        """Test my subscription view when user has no wallet"""
        self.wallet.delete()
        self.login_user()
        
        url = reverse('subscriptions:my_subscription')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertDecimalEqual(
            response.context['wallet_balance'],
            Decimal('0.00')
        )

    def test_my_subscription_history_ordering(self):
        """Test subscription history is properly ordered"""
        # Create multiple subscriptions
        old_sub = self.create_subscription(
            plan=self.basic_plan,
            status='expired'
        )
        import time
        time.sleep(1)  # ensure timestamp difference
        new_sub = self.create_subscription(
            plan=self.premium_plan,
            status='active'
        )
        
        self.login_user()
        
        url = reverse('subscriptions:my_subscription')
        response = self.client.get(url)
        
        history = list(response.context['subscription_history'])
        # Should be ordered by created_at descending (newest first)
        self.assertEqual(history[0], new_sub)
        self.assertEqual(history[1], old_sub)


class ToggleAutoRenewalViewTest(BaseViewTestCase):
    """Test toggle_auto_renewal view"""

    def test_toggle_auto_renewal_anonymous_user_redirects(self):
        """Test anonymous user is redirected to login"""
        url = reverse('subscriptions:toggle_auto_renewal')
        response = self.client.post(url)
        
        expected_url = f'/login/?next={url}'
        self.assertRedirects(response, expected_url)

    def test_toggle_auto_renewal_get_redirects(self):
        """Test GET request redirects to my_subscription"""
        self.login_user()
        
        url = reverse('subscriptions:toggle_auto_renewal')
        response = self.client.get(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))

    def test_toggle_auto_renewal_enable(self):
        """Test enabling auto renewal"""
        subscription = self.create_subscription(auto_renewal=False)
        self.login_user()
        
        url = reverse('subscriptions:toggle_auto_renewal')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check auto renewal was enabled
        subscription.refresh_from_db()
        self.assertTrue(subscription.auto_renewal)
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Auto-renewal enabled', str(messages[0]))

    def test_toggle_auto_renewal_disable(self):
        """Test disabling auto renewal"""
        subscription = self.create_subscription(auto_renewal=True)
        self.login_user()
        
        url = reverse('subscriptions:toggle_auto_renewal')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check auto renewal was disabled
        subscription.refresh_from_db()
        self.assertFalse(subscription.auto_renewal)
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Auto-renewal disabled', str(messages[0]))

    def test_toggle_auto_renewal_no_active_subscription(self):
        """Test toggle auto renewal without active subscription"""
        self.login_user()
        
        url = reverse('subscriptions:toggle_auto_renewal')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('No active subscription found', str(messages[0]))

    def test_toggle_auto_renewal_expired_subscription(self):
        """Test toggle auto renewal with expired subscription"""
        past_date = timezone.now() - timedelta(days=1)
        self.create_subscription(
            expiry_date=past_date,
            auto_renewal=True
        )
        self.login_user()
        
        url = reverse('subscriptions:toggle_auto_renewal')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('No active subscription found', str(messages[0]))


class CancelSubscriptionViewTest(BaseViewTestCase):
    """Test cancel_subscription view"""

    def test_cancel_subscription_anonymous_user_redirects(self):
        """Test anonymous user is redirected to login"""
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.post(url)
        
        expected_url = f'/login/?next={url}'
        self.assertRedirects(response, expected_url)

    def test_cancel_subscription_get_redirects(self):
        """Test GET request redirects to my_subscription"""
        self.login_user()
        
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.get(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))

    @patch('wallets.services.WalletService.credit_wallet')
    def test_cancel_subscription_within_6_hours_with_refund(self, mock_credit):
        """Test cancellation within 6 hours gets refund"""
        # Create subscription that started 2 hours ago
        start_time = timezone.now() - timedelta(hours=2)
        subscription = self.create_subscription()
        subscription.start_date = start_time
        subscription.save()
        
        self.login_user()
        
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check subscription was cancelled
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'cancelled')
        
        # Check refund was processed
        mock_credit.assert_called_once_with(
            user=self.user,
            amount=subscription.plan.price,
            category='subscription_refund',
            description=f"Refund for {subscription.plan.name} (cancelled within 6 hours)",
            reference=f"REFUND_{self.user.id}_{subscription.id}"
        )
        
        # Check success message with refund info
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('refunded to your wallet', str(messages[0]))

    def test_cancel_subscription_after_6_hours_no_refund(self):
        """Test cancellation after 6 hours doesn't get refund"""
        # Create subscription that started 8 hours ago
        start_time = timezone.now() - timedelta(hours=8)
        subscription = self.create_subscription()
        subscription.start_date = start_time
        subscription.save()
        
        self.login_user()
        
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check subscription was cancelled
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'cancelled')
        
        # Check success message without refund info
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('no refund, beyond 6 hours', str(messages[0]))

    def test_cancel_subscription_no_active_subscription(self):
        """Test cancel subscription without active subscription"""
        self.login_user()
        
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('No active subscription found', str(messages[0]))

    @patch('tasks.services.TaskWalletService.debit_wallet')
    @patch('tasks.services.TaskWalletService.get_or_create_wallet')
    @patch('wallets.services.WalletService.credit_wallet')
    def test_cancel_business_plan_with_full_task_wallet_balance(
        self, mock_credit, mock_get_wallet, mock_debit
    ):
        """Test cancelling business plan with full task wallet balance allows refund"""
        # Mock task wallet with full balance
        mock_task_wallet = MagicMock()
        mock_task_wallet.balance = Decimal('10.00')
        mock_get_wallet.return_value = mock_task_wallet
        mock_debit.return_value = True
        
        # Create business plan subscription within refund window
        start_time = timezone.now() - timedelta(hours=2)
        subscription = self.create_subscription(plan=self.business_plan)
        subscription.start_date = start_time
        subscription.save()
        
        self.login_user()
        
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check subscription was cancelled
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'cancelled')
        
        # Check task wallet allocation was reversed
        mock_debit.assert_called_once_with(
            user=self.user,
            amount=Decimal("10.00"),
            category="subscription_allocation_reversal",
            description=f"Reversal of monthly allocation from cancelled plan {subscription.plan.name}"
        )
        
        # Check refund was processed
        mock_credit.assert_called_once()
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('refunded to your wallet', str(messages[0]))

    @patch('tasks.services.TaskWalletService.get_or_create_wallet')
    def test_cancel_business_plan_with_partial_task_wallet_balance(self, mock_get_wallet):
        """Test cancelling business plan with spent task wallet funds blocks refund"""
        # Mock task wallet with partial balance (user spent some)
        mock_task_wallet = MagicMock()
        mock_task_wallet.balance = Decimal('5.00')  # Only half remaining
        mock_get_wallet.return_value = mock_task_wallet
        
        # Create business plan subscription within refund window
        start_time = timezone.now() - timedelta(hours=2)
        subscription = self.create_subscription(plan=self.business_plan)
        subscription.start_date = start_time
        subscription.save()
        
        self.login_user()
        
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check subscription was cancelled
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'cancelled')
        
        # Check warning message about no refund
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('refund is not possible', str(messages[0]))
        self.assertIn('already spent the Task Wallet allocation', str(messages[0]))

    @patch('tasks.services.TaskWalletService.get_or_create_wallet')
    def test_cancel_business_plan_with_zero_task_wallet_balance(self, mock_get_wallet):
        """Test cancelling business plan with zero task wallet balance blocks refund"""
        # Mock task wallet with zero balance (user spent all)
        mock_task_wallet = MagicMock()
        mock_task_wallet.balance = Decimal('0.00')
        mock_get_wallet.return_value = mock_task_wallet
        
        # Create business plan subscription within refund window
        start_time = timezone.now() - timedelta(hours=2)
        subscription = self.create_subscription(plan=self.business_plan)
        subscription.start_date = start_time
        subscription.save()
        
        self.login_user()
        
        url = reverse('subscriptions:cancel_subscription')
        response = self.client.post(url)
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check subscription was cancelled
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'cancelled')
        
        # Check warning message about no refund
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('refund is not possible', str(messages[0]))
        self.assertIn('already spent the Task Wallet allocation', str(messages[0]))

    def test_cancel_non_business_plan_gets_normal_refund(self):
        """Test cancelling non-business plan works normally"""
        # Create basic plan subscription within refund window
        start_time = timezone.now() - timedelta(hours=2)
        subscription = self.create_subscription(plan=self.basic_plan)
        subscription.start_date = start_time
        subscription.save()
        
        self.login_user()
        
        with patch('wallets.services.WalletService.credit_wallet') as mock_credit:
            url = reverse('subscriptions:cancel_subscription')
            response = self.client.post(url)
            
            self.assertRedirects(response, reverse('subscriptions:my_subscription'))
            
            # Check subscription was cancelled
            subscription.refresh_from_db()
            self.assertEqual(subscription.status, 'cancelled')
            
            # Check refund was processed normally
            mock_credit.assert_called_once()
            
            # Check success message
            messages = list(get_messages(response.wsgi_request))
            self.assertEqual(len(messages), 1)
            self.assertIn('refunded to your wallet', str(messages[0]))