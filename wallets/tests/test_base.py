# wallets/tests/test_base.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from decimal import Decimal
from unittest.mock import patch
import uuid

from django.utils import timezone
from datetime import timedelta

from ..models import Wallet, Transaction
from ..services import WalletService
from tasks.models import Task
from subscriptions.models import UserSubscription, SubscriptionPlan
from payments.models import PaymentGateway

User = get_user_model()


class BaseWalletTestCase(TestCase):
    """Base test case with common setup for wallet tests"""
    
    @classmethod
    def setUpTestData(cls):
        # Create test users
        cls.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        cls.admin_user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
            is_staff=True
        )
        cls.other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        
        # Create company system user
        cls.company_user = User.objects.create_user(
            username='system_company',
            email='system@company.com',
            password='systempass123'
        )
        
        # Create subscription plans
        cls.basic_plan = SubscriptionPlan.objects.create(
            name="Basic Member Plan",
            price=Decimal('9.99'),
            duration_days=30,
            daily_ad_limit=5
        )
        cls.business_plan = SubscriptionPlan.objects.create(
            name="Business Member Account",
            price=Decimal('29.99'),
            duration_days=30,
            daily_ad_limit=20
        )

        cls.gateway = PaymentGateway.objects.create(
            name="paystack",
            is_active=True
        )
        
    def setUp(self):
        # Create wallets
        self.admin_user.is_staff = True
        self.admin_user.is_superuser = True
        self.admin_user.save()

        self.wallet = WalletService.get_or_create_wallet(self.user)
        self.admin_wallet = WalletService.get_or_create_wallet(self.admin_user)
        self.other_wallet = WalletService.get_or_create_wallet(self.other_user)

        
        
    def create_subscription(self, user=None, plan=None, **kwargs) :
        """Create a user subscription"""
        if user is None:
            user = self.user
        if plan is None:
            plan = self.basic_plan
            
        defaults = {
            'user': user,
            'plan': plan,
            'start_date': timezone.now(),
            'expiry_date': timezone.now() + timedelta(days=plan.duration_days),
            'status': 'active',
            'auto_renewal': True
        }
        defaults.update(kwargs)
        return UserSubscription.objects.create(**defaults)
    
    def create_funded_wallet(self, user, amount):
        """Helper to create a wallet with funds"""
        wallet = WalletService.get_or_create_wallet(user)
        WalletService.credit_wallet(
            user=user,
            amount=amount,
            category='funding',
            description='Test funding'
        )
        return wallet
    
    def create_withdrawal_request(self, user, amount=Decimal('100.00')):
        """Helper to create withdrawal request"""
        account_details = {
            'account_number': '1234567890',
            'account_name': 'Test Account',
            'bank_name': 'Test Bank',
            'bank_code': '001'
        }
        return WalletService.create_withdrawal_request(
            user=user,
            amount=amount,
            withdrawal_method='paystack',
            account_details=account_details
        )
    

    def create_task(self, advertiser, title="Test Task", payout_per_slot=Decimal('5.00'), total_slots=10):
        """Helper to create a Task for tests"""
        return Task.objects.create(
            advertiser=advertiser,
            title=title,
            description="Test task description",
            payout_per_slot=payout_per_slot,
            total_slots=total_slots,
            deadline=timezone.now() + timedelta(days=7),
            proof_instructions="Upload a screenshot as proof."
        )



class PermissionTestMixin:
    """Mixin for testing view permissions"""
    
    def assert_requires_login(self, url, method='get', data=None):
        """Assert that URL requires login"""
        response = getattr(self.client, method)(url, data=data or {})
        self.assertIn(response.status_code, [302, 401, 403])
        
    def assert_requires_staff(self, url, method='get', data=None):
        """Assert that URL requires staff status"""
        self.client.force_login(self.user)
        response = getattr(self.client, method)(url, data=data or {})
        self.assertIn(response.status_code, [302, 403])
        
    def assert_requires_subscription(self, url, method='get', data=None):
        """Assert that URL requires active subscription"""
        self.client.force_login(self.user)
        response = getattr(self.client, method)(url, data=data or {})
        # Assuming subscription_required decorator redirects
        self.assertEqual(response.status_code, 302)


class MockPaystackMixin:
    """Mixin for mocking Paystack service calls"""
    
    def mock_paystack_success(self):
        """Mock successful Paystack responses"""
        self.paystack_patcher = patch('wallets.services.PaystackService')
        mock_paystack = self.paystack_patcher.start()
        
        # Mock successful transfer recipient creation
        mock_paystack.return_value.create_transfer_recipient.return_value = {
            'success': True,
            'data': {
                'data': {
                    'recipient_code': 'RCP_test123',
                    'name': 'Test Account'
                }
            }
        }
        
        # Mock successful transfer initiation
        mock_paystack.return_value.initiate_transfer.return_value = {
            'success': True,
            'data': {
                'transaction_id': str(uuid.uuid4()),
                'reference': 'TRF_test123',
                'transfer_code': 'TRF_test456',
                'raw': {'status': 'success'}
            }
        }
        
        # Mock successful payment initialization
        mock_paystack.return_value.initialize_payment.return_value = {
            'success': True,
            'data': {
                'transaction_id': str(uuid.uuid4()),
                'authorization_url': 'https://checkout.paystack.com/test123',
                'reference': 'PAY_test123'
            }
        }
        
        return mock_paystack.return_value
    
    def mock_paystack_failure(self):
        """Mock failed Paystack responses"""
        self.paystack_patcher = patch('wallets.services.PaystackService')
        mock_paystack = self.paystack_patcher.start()
        
        mock_paystack.return_value.create_transfer_recipient.return_value = {
            'success': False,
            'error': 'Failed to create recipient'
        }
        
        mock_paystack.return_value.initiate_transfer.return_value = {
            'success': False,
            'error': 'Transfer failed'
        }
        
        mock_paystack.return_value.initialize_payment.return_value = {
            'success': False,
            'error': 'Payment initialization failed'
        }
        
        return mock_paystack.return_value
    
    def tearDown(self):
        if hasattr(self, 'paystack_patcher'):
            self.paystack_patcher.stop()
        super().tearDown()


class TransactionTestMixin:
    """Mixin for transaction-related test helpers"""
    
    def assert_transaction_created(self, user, transaction_type, category, amount):
        """Assert that a transaction was created with specific parameters"""
        transaction = Transaction.objects.filter(
            user=user,
            transaction_type=transaction_type,
            category=category,
            amount=amount
        ).first()
        self.assertIsNotNone(transaction, 
            f"Transaction not found: {transaction_type} {category} {amount}")
        return transaction
    
    def assert_wallet_balance(self, user, expected_balance):
        """Assert wallet balance matches expected value"""
        wallet = Wallet.objects.get(user=user)
        self.assertEqual(
            wallet.balance, 
            Decimal(str(expected_balance)),
            f"Expected balance {expected_balance}, got {wallet.balance}"
        )
    
    def assert_balance_change(self, user, initial_balance, expected_change):
        """Assert that wallet balance changed by expected amount"""
        wallet = Wallet.objects.get(user=user)
        expected_final = Decimal(str(initial_balance)) + Decimal(str(expected_change))
        self.assertEqual(
            wallet.balance,
            expected_final,
            f"Expected balance change of {expected_change}, "
            f"from {initial_balance} to {expected_final}, got {wallet.balance}"
        )


class FormTestMixin:
    """Mixin for form testing utilities"""
    
    def assert_form_error(self, response, form_name, field_name, error_message=None):
        """Assert that form has specific field error"""
        self.assertFormError(response, form_name, field_name, error_message)
    
    def assert_form_valid(self, form_class, data):
        """Assert that form is valid with given data"""
        form = form_class(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        return form
    
    def assert_form_invalid(self, form_class, data, expected_errors=None):
        """Assert that form is invalid with given data"""
        form = form_class(data=data)
        self.assertFalse(form.is_valid())
        if expected_errors:
            for field, error in expected_errors.items():
                self.assertIn(error, form.errors.get(field, []))
        return form


class ViewTestMixin:
    """Mixin for view testing utilities"""
    
    def assert_template_used(self, response, template_name):
        """Assert specific template was used"""
        self.assertTemplateUsed(response, template_name)
    
    def assert_context_contains(self, response, key, value=None):
        """Assert response context contains key, optionally with specific value"""
        self.assertIn(key, response.context)
        if value is not None:
            self.assertEqual(response.context[key], value)
    
    def assert_message_displayed(self, response, message_text, level=None):
        """Assert that a message was displayed"""
        messages = list(response.context.get('messages', []))
        message_texts = [str(msg) for msg in messages]
        self.assertIn(message_text, message_texts)
        
        if level is not None:
            message_levels = [msg.level for msg in messages 
                            if str(msg) == message_text]
            self.assertIn(level, message_levels)


# Combined base class for most tests
class WalletTestCase(BaseWalletTestCase, PermissionTestMixin, MockPaystackMixin,
                     TransactionTestMixin, FormTestMixin, ViewTestMixin):
    """Combined base class for wallet tests with all mixins"""
    pass


# Settings override for tests
class TestSettings:
    """Test-specific settings"""
    COMPANY_SYSTEM_USERNAME = 'system_company'
    
    # Payment gateway settings for tests
    PAYSTACK_PUBLIC_KEY = 'pk_test_123'
    PAYSTACK_SECRET_KEY = 'sk_test_123'
    
    # Test database settings
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }

    