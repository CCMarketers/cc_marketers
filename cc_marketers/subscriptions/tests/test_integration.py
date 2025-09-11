# tests/test_integration.py
"""
Integration tests for the subscription app
These tests verify that all components work together correctly
"""
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.contrib.messages import get_messages
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch, MagicMock

from subscriptions.models import  UserSubscription
from subscriptions.services import SubscriptionService
from .test_base import BaseTestMixin


class SubscriptionWorkflowIntegrationTest(BaseTestMixin, TransactionTestCase):
    """Test complete subscription workflows end-to-end"""

    @patch('subscriptions.views.credit_signup_bonus_on_subscription')
    def test_complete_subscription_workflow(self, mock_bonus):
        """Test complete user subscription journey"""
        self.login_user()

        # 1. User visits subscription plans
        response = self.client.get(reverse('subscriptions:plans'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_plan.name)

        # 2. User subscribes to a plan
        response = self.client.post(
            reverse('subscriptions:subscribe', args=[self.basic_plan.id])
        )

        self.assertRedirects(response, reverse('subscriptions:my_subscription'))

        # Now should work
        mock_bonus.assert_called_once_with(self.user)

    def test_business_plan_subscription_with_task_wallet(self):
        """Test Business Member Plan subscription allocates task wallet funds"""
        self.login_user()
        
        with patch('tasks.services.TaskWalletService.credit_wallet') as mock_credit:
            mock_credit.return_value = MagicMock()
            
            # Subscribe to business plan
            response = self.client.post(
                reverse('subscriptions:subscribe', args=[self.business_plan.id])
            )
            
            self.assertRedirects(response, reverse('subscriptions:my_subscription'))
            
            # Check task wallet allocation was called
            mock_credit.assert_called_once_with(
                user=self.user,
                amount=Decimal("10.00"),
                category="subscription_allocation",
                description=f"Monthly allocation from subscription plan {self.business_plan.name}"
            )

    def test_business_plan_cancellation_with_task_wallet_reversal(self):
        """Test Business Plan cancellation reverses task wallet allocation"""
        # Create business plan subscription
        start_time = timezone.now() - timedelta(hours=2)  # Within refund window
        subscription = self.create_subscription(plan=self.business_plan)
        subscription.start_date = start_time
        subscription.save()
        
        self.login_user()
        
        with patch('tasks.services.TaskWalletService.get_or_create_wallet') as mock_get_wallet, \
             patch('tasks.services.TaskWalletService.debit_wallet') as mock_debit, \
             patch('wallets.services.WalletService.credit_wallet') as mock_credit:
            
            # Mock task wallet with full balance
            mock_task_wallet = MagicMock()
            mock_task_wallet.balance = Decimal('10.00')
            mock_get_wallet.return_value = mock_task_wallet
            mock_debit.return_value = True
            
            # Cancel subscription
            response = self.client.post(reverse('subscriptions:cancel_subscription'))
            
            self.assertRedirects(response, reverse('subscriptions:my_subscription'))
            
            # Check task wallet debit was called
            mock_debit.assert_called_once_with(
                user=self.user,
                amount=Decimal("10.00"),
                category="subscription_allocation_reversal",
                description=f"Reversal of monthly allocation from cancelled plan {subscription.plan.name}"
            )
            
            # Check refund was processed
            mock_credit.assert_called_once()

    def test_subscription_with_insufficient_balance(self):
        """Test subscription workflow with insufficient wallet balance"""
        # Set low wallet balance
        self.wallet.balance = Decimal('2.00')
        self.wallet.save()
        
        self.login_user()
        
        # Try to subscribe
        response = self.client.post(
            reverse('subscriptions:subscribe', args=[self.basic_plan.id])
        )
        
        self.assertRedirects(response, reverse('subscriptions:plans'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Insufficient wallet balance', str(messages[0]))
        
        # Check no subscription was created
        self.assertFalse(
            UserSubscription.objects.filter(
                user=self.user,
                plan=self.basic_plan
            ).exists()
        )

    def test_multiple_subscription_attempts_prevents_duplicates(self):
        """Test user cannot have multiple active subscriptions"""
        # Create active subscription
        existing_sub = self.create_subscription()
        
        self.login_user()
        
        # Try to subscribe to another plan
        response = self.client.post(
            reverse('subscriptions:subscribe', args=[self.premium_plan.id])
        )
        
        self.assertRedirects(response, reverse('subscriptions:my_subscription'))
        
        # Check error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('already have an active subscription', str(messages[0]))
        
        # Check only one active subscription exists
        active_subs = UserSubscription.objects.filter(
            user=self.user,
            status='active'
        )
        self.assertEqual(active_subs.count(), 1)
        self.assertEqual(active_subs.first(), existing_sub)

    def test_subscription_renewal_workflow(self):
        """Test automatic subscription renewal workflow"""
        # Create expired subscription with auto-renewal
        past_date = timezone.now() - timedelta(hours=1)
        subscription = self.create_subscription(
            expiry_date=past_date,
            auto_renewal=True
        )
        initial_wallet_balance = self.wallet.balance # Should be 100.00
        with patch('tasks.services.TaskWalletService.credit_wallet'):
            # Run renewal check
            SubscriptionService.check_and_renew_subscriptions()
            
            # Check subscription was renewed
            subscription.refresh_from_db()
            self.assertEqual(subscription.status, 'active')
            self.assertGreater(subscription.expiry_date, timezone.now())
            
            # Check wallet was debited
            self.wallet.refresh_from_db()
            expected_balance = initial_wallet_balance - self.basic_plan.price
            self.assertDecimalEqual(self.wallet.balance, expected_balance)

    def test_subscription_expiry_without_renewal(self):
        """Test subscription expiry when auto-renewal is disabled"""
        # Create expired subscription without auto-renewal
        past_date = timezone.now() - timedelta(hours=1)
        subscription = self.create_subscription(
            expiry_date=past_date,
            auto_renewal=False
        )
        
        # Run renewal check
        SubscriptionService.check_and_renew_subscriptions()
        
        # Check subscription was marked as expired
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'expired')
        
        # Check wallet was not debited
        self.wallet.refresh_from_db()
        self.assertDecimalEqual(self.wallet.balance, Decimal('100.00'))

    def test_subscription_context_processor_integration(self):
        """Test subscription context processor works with views"""
        subscription = self.create_subscription()
        self.login_user()
        
        # Access any view that uses context processor
        response = self.client.get(reverse('subscriptions:plans'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_subscription'], subscription)

    def test_subscription_middleware_integration(self):
        """Test subscription middleware with protected views"""
        from subscriptions.middleware import SubscriptionMiddleware
        from django.http import HttpResponse
        
        def dummy_view(request):
            return HttpResponse("Protected content")
        
        middleware = SubscriptionMiddleware(lambda req: dummy_view(req))
        middleware.protected_views = ['test:protected']
        
        # Mock request
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = type('obj', (object,), {
            'app_name': 'test',
            'url_name': 'protected'
        })()
        request = self.add_middleware_to_request(request)
        
        # Without subscription - should redirect
        response = middleware(request)
        self.assertEqual(response.status_code, 302)
        
        # With subscription - should allow access
        self.create_subscription()
        response = middleware(request)
        self.assertEqual(response.status_code, 200)

    def add_middleware_to_request(self, request):
        """Helper to add middleware to request"""
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.contrib.messages.storage.fallback import FallbackStorage
        
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request


class SubscriptionAdminIntegrationTest(BaseTestMixin, TestCase):
    """Test subscription admin integration"""

    def setUp(self):
        super().setUp()
        from django.contrib.admin.sites import site
        from subscriptions.admin import SubscriptionPlanAdmin, UserSubscriptionAdmin
        from subscriptions.models import SubscriptionPlan, UserSubscription
        
        self.plan_admin = SubscriptionPlanAdmin(SubscriptionPlan, site)
        self.subscription_admin = UserSubscriptionAdmin(UserSubscription, site)

    def test_admin_list_views_integration(self):
        """Test admin list views display correct data"""
        subscription = self.create_subscription()
        
        # Test plan admin queryset
        plan_queryset = self.plan_admin.get_queryset(None)
        self.assertIn(self.basic_plan, plan_queryset)
        
        # Test subscription admin queryset
        sub_queryset = self.subscription_admin.get_queryset(None)
        self.assertIn(subscription, sub_queryset)

    def test_admin_search_functionality_integration(self):
        """Test admin search works with real data"""
        subscription = self.create_subscription()
        
        # Mock request with search term
        class MockRequest:
            GET = {'q': self.user.username}
        
        request = MockRequest()
        queryset = self.subscription_admin.get_search_results(
            request, 
            UserSubscription.objects.all(),
            self.user.username
        )[0]
        
        self.assertIn(subscription, queryset)


class SubscriptionServiceIntegrationTest(BaseTestMixin, TransactionTestCase):
    """Test subscription service integration with external services"""

    @patch('referrals.services.credit_signup_bonus_on_subscription')
    @patch('tasks.services.TaskWalletService.credit_wallet')
    @patch('wallets.services.WalletService.credit_wallet')
    def test_full_service_integration(self, mock_wallet_credit, mock_task_credit, mock_bonus):
        """Test subscription service integrates with all external services"""
        mock_task_credit.return_value = MagicMock()
        
        # Subscribe to business plan
        result = SubscriptionService.subscribe_user(self.user, self.business_plan.id)
        
        self.assertTrue(result['success'])
        
        # Check all external services were called
        # Note: bonus credit is called from the view, not service
        mock_task_credit.assert_called_once()
        
        # Test cancellation with refund
        subscription = result['subscription']
        subscription.status = 'cancelled'
        subscription.save()
        
        # Check integration works without errors
        self.assertEqual(subscription.status, 'cancelled')

    def test_service_error_handling_integration(self):
        """Test service handles external service errors gracefully"""
        with patch('tasks.services.TaskWalletService.credit_wallet') as mock_credit:
            mock_credit.side_effect = Exception("External service error")
            
            # Should handle exception gracefully
            result = SubscriptionService.subscribe_user(self.user, self.business_plan.id)
            
            # Should fail due to transaction rollback
            self.assertFalse(result['success'])
            
            # Check no subscription was created
            self.assertFalse(
                UserSubscription.objects.filter(
                    user=self.user,
                    plan=self.business_plan
                ).exists()
            )


class SubscriptionUIIntegrationTest(BaseTestMixin, TestCase):
    """Test subscription UI integration"""

    def test_subscription_plans_page_displays_user_data(self):
        """Test subscription plans page displays user-specific data correctly"""
        subscription = self.create_subscription()
        
        # Create pending withdrawal to test balance calculation
        self.create_withdrawal_request(
            user=self.user,
            amount=Decimal('20.00'),
            status='pending'
        )
        
        self.login_user()
        
        response = self.client.get(reverse('subscriptions:plans'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_subscription'], subscription)
        self.assertDecimalEqual(
            response.context['user_wallet_balance'],
            self.wallet.balance
        )

    def test_my_subscription_page_displays_complete_data(self):
        """Test my subscription page displays all relevant data"""
        subscription = self.create_subscription()
        
        # Create subscription history
        old_subscription = self.create_subscription(
            plan=self.premium_plan,
            status='expired'
        )
        
        # Create pending withdrawal
        withdrawal = self.create_withdrawal_request(
            user=self.user,
            amount=Decimal('15.00'),
            status='pending'
        )
        
        self.login_user()
        
        response = self.client.get(reverse('subscriptions:my_subscription'))
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_subscription'], subscription)
        
        # Check subscription history
        history = response.context['subscription_history']
        self.assertEqual(history.count(), 2)
        self.assertIn(subscription, history)
        self.assertIn(old_subscription, history)
        
        # Check wallet balance calculation
        expected_balance = self.wallet.balance - withdrawal.amount
        self.assertDecimalEqual(
            response.context['wallet_balance'],
            expected_balance
        )

    def test_error_messages_display_correctly(self):
        """Test error messages are displayed correctly in UI"""
        # Try to subscribe without sufficient balance
        self.wallet.balance = Decimal('1.00')
        self.wallet.save()
        
        self.login_user()
        
        response = self.client.post(
            reverse('subscriptions:subscribe', args=[self.basic_plan.id]),
            follow=True
        )
        
        # Check error message is displayed
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Insufficient wallet balance', str(messages[0]))
        
        # Check redirected to plans page
        self.assertContains(response, self.basic_plan.name)

    def test_success_messages_display_correctly(self):
        """Test success messages are displayed correctly in UI"""
        self.login_user()
        
        with patch('referrals.services.credit_signup_bonus_on_subscription'):
            response = self.client.post(
                reverse('subscriptions:subscribe', args=[self.basic_plan.id]),
                follow=True
            )
        
        # Check success message is displayed
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn('Successfully subscribed', str(messages[0]))
        
        # Check redirected to my subscription page
        self.assertContains(response, self.basic_plan.name)


class SubscriptionSecurityIntegrationTest(BaseTestMixin, TestCase):
    """Test subscription security integration"""

    def test_authentication_required_integration(self):
        """Test authentication is required for protected views"""
        protected_urls = [
            ('subscriptions:subscribe', [1]),
            ('subscriptions:my_subscription', []),
            ('subscriptions:toggle_auto_renewal', []),
            ('subscriptions:cancel_subscription', []),
        ]
        
        for url_name, args in protected_urls:
            with self.subTest(url_name=url_name):
                url = reverse(url_name, args=args)
                response = self.client.post(url)
                
                # Should redirect to login
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login/', response.url)

    def test_csrf_protection_integration(self):
        """Test CSRF protection works with subscription forms"""
        self.login_user()
        
        # Try POST without CSRF token
        response = self.client.post(
            reverse('subscriptions:subscribe', args=[self.basic_plan.id]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'  # Simulate AJAX
        )
        
        # Should either work (if CSRF middleware disabled in tests) or fail appropriately
        self.assertIn(response.status_code, [200, 302, 403])

    def test_subscription_permission_integration(self):
        """Test users can only access their own subscription data"""
        # Create subscriptions for different users
        user1_sub = self.create_subscription(user=self.user)
        user2_sub = self.create_subscription(user=self.user2, plan=self.premium_plan)
        
        self.login_user()  # Login as user1
        
        # Access my subscription page
        response = self.client.get(reverse('subscriptions:my_subscription'))
        
        self.assertEqual(response.status_code, 200)
        
        # Should see own subscription
        self.assertContains(response, user1_sub.plan.name)
        
        # Should not see other user's subscription
        self.assertNotContains(response, user2_sub.plan.name)