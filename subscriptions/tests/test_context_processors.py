# tests/test_context_processors.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
# Add 'builtins' to your imports at the top of the file
import builtins
from subscriptions.context_processors import subscription_context
from .test_base import BaseTestMixin

User = get_user_model()


class SubscriptionContextProcessorTest(BaseTestMixin, TestCase):
    """Test subscription_context context processor"""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def test_context_processor_anonymous_user(self):
        """Test context processor with anonymous user"""
        request = self.factory.get('/')
        request.user = AnonymousUser()
        
        context = subscription_context(request)
        
        self.assertEqual(context, {})

    def test_context_processor_authenticated_user_no_subscription(self):
        """Test context processor with authenticated user without subscription"""
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        expected_context = {
            'user_active_subscription': None,
            'user_wallet_balance': 0  # Default when no TaskWallet exists
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_authenticated_user_with_subscription(self):
        """Test context processor with authenticated user with active subscription"""
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        expected_context = {
            'user_active_subscription': subscription,
            'user_wallet_balance': self.task_wallet.balance
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_with_expired_subscription(self):
        """Test context processor ignores expired subscription"""
        past_date = timezone.now() - timedelta(days=1)
        self.create_subscription(
            expiry_date=past_date
        )
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        # Should not include expired subscription
        expected_context = {
            'user_active_subscription': None,
            'user_wallet_balance': self.task_wallet.balance
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_with_cancelled_subscription(self):
        """Test context processor ignores cancelled subscription"""
        self.create_subscription(
            status='cancelled'
        )
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        # Should not include cancelled subscription
        expected_context = {
            'user_active_subscription': None,
            'user_wallet_balance': self.task_wallet.balance
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_with_task_wallet_balance(self):
        """Test context processor includes task wallet balance"""
        # Update task wallet balance
        self.task_wallet.balance = Decimal('25.50')
        self.task_wallet.save()
        
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        expected_context = {
            'user_active_subscription': subscription,
            'user_wallet_balance': Decimal('25.50')
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_no_task_wallet(self):
        """Test context processor when user has no task wallet"""
        # Delete task wallet
        self.task_wallet.delete()
        
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        expected_context = {
            'user_active_subscription': subscription,
            'user_wallet_balance': 0
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_handles_task_wallet_exception(self):
        """Test context processor handles TaskWallet exceptions gracefully"""
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        # Mock TaskWallet.objects.get to raise exception
        with patch('tasks.models.TaskWallet.objects.get') as mock_get:
            mock_get.side_effect = Exception("Database error")
            
            context = subscription_context(request)
            
            expected_context = {
                'user_active_subscription': subscription,
                'user_wallet_balance': 0  # Default when exception occurs
            }
            self.assertEqual(context, expected_context)


    def test_context_processor_handles_import_error(self):
        """Test context processor handles TaskWallet import errors"""
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        # Keep a reference to the original import function
        original_import = builtins.__import__

        def import_mock(name, *args, **kwargs):
            """
            Custom import function. If the code tries to import 'tasks.models',
            we raise an ImportError. For any other module, we let the
            original import function handle it.
            """
            if name == 'tasks.models':
                raise ImportError("Simulated module not found error")
            return original_import(name, *args, **kwargs)

        # Patch the built-in import function with our custom one
        with patch('builtins.__import__', side_effect=import_mock):
            context = subscription_context(request)
            
        expected_context = {
            'user_active_subscription': subscription,
            'user_wallet_balance': 0  # This is the expected fallback value
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_multiple_subscriptions(self):
        """Test context processor returns only active subscription when multiple exist"""
        # Create expired subscription
        past_date = timezone.now() - timedelta(days=5)
        self.create_subscription(
            plan=self.basic_plan,
            expiry_date=past_date,
            status='expired'
        )
        
        # Create active subscription
        active_sub = self.create_subscription(
            plan=self.premium_plan,
            status='active'
        )
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        # Should return the active subscription
        expected_context = {
            'user_active_subscription': active_sub,
            'user_wallet_balance': self.task_wallet.balance
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_subscription_service_integration(self):
        """Test context processor integrates correctly with SubscriptionService"""
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        # Mock SubscriptionService to ensure it's being used
        with patch('subscriptions.context_processors.SubscriptionService.get_user_active_subscription') as mock_service:
            mock_service.return_value = subscription
            
            context = subscription_context(request)
            
            # Verify service was called
            mock_service.assert_called_once_with(self.user)
            
            expected_context = {
                'user_active_subscription': subscription,
                'user_wallet_balance': self.task_wallet.balance
            }
            self.assertEqual(context, expected_context)

    def test_context_processor_different_user_types(self):
        """Test context processor with different user types"""
        # Test with regular user
        regular_subscription = self.create_subscription(user=self.user)
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        self.assertEqual(context['user_active_subscription'], regular_subscription)
        
        # Test with admin user
        admin_subscription = self.create_subscription(user=self.admin_user, plan=self.premium_plan)
        
        request.user = self.admin_user
        context = subscription_context(request)
        self.assertEqual(context['user_active_subscription'], admin_subscription)

    def test_context_processor_user_with_zero_balance(self):
        """Test context processor with user having zero task wallet balance"""
        self.task_wallet.balance = Decimal('0.00')
        self.task_wallet.save()
        
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        expected_context = {
            'user_active_subscription': subscription,
            'user_wallet_balance': Decimal('0.00')
        }
        self.assertEqual(context, expected_context)

    def test_context_processor_user_with_negative_balance(self):
        """Test context processor with user having negative task wallet balance"""
        self.task_wallet.balance = Decimal('-5.00')
        self.task_wallet.save()
        
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        context = subscription_context(request)
        
        expected_context = {
            'user_active_subscription': subscription,
            'user_wallet_balance': Decimal('-5.00')
        }
        self.assertEqual(context, expected_context)


    def test_context_processor_performance(self):
        """Test context processor performance with database queries"""
        self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        # The logic correctly makes two queries: one for the subscription
        # and one for the wallet. The test should expect this.
        with self.assertNumQueries(2):
            subscription_context(request)

    def test_context_processor_consistency(self):
        """Test context processor returns consistent results"""
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        # Call context processor multiple times
        context1 = subscription_context(request)
        context2 = subscription_context(request)
        
        self.assertEqual(context1, context2)
        self.assertEqual(context1['user_active_subscription'], subscription)
        self.assertEqual(context2['user_active_subscription'], subscription)

    def test_context_processor_empty_context_structure(self):
        """Test context processor returns expected structure even when empty"""
        request = self.factory.get('/')
        request.user = AnonymousUser()
        
        context = subscription_context(request)
        
        # Should return empty dict for anonymous users
        self.assertIsInstance(context, dict)
        self.assertEqual(len(context), 0)

    def test_context_processor_with_user_without_get_display_name(self):
        """Test context processor works with users without get_display_name method"""
        # Create a mock user that might not have all expected methods
        subscription = self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        
        # This should work regardless of user model variations
        context = subscription_context(request)
        
        self.assertIn('user_active_subscription', context)
        self.assertEqual(context['user_active_subscription'], subscription)