# payments/tests/test_base.py
import uuid
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from unittest.mock import Mock

from payments.models import PaymentGateway, PaymentTransaction, PaystackTransaction, WebhookEvent
from wallets.models import Wallet

User = get_user_model()


class BaseTestCase(TestCase):
    """Base test case with common setup and utilities"""
    
    @classmethod
    def setUpTestData(cls):
        """Set up test data for all test methods"""
        # Create test users
        cls.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='testpassword123',
            first_name='Test',
            last_name='User'
        )
        
        cls.other_user = User.objects.create_user(
            username='otheruser',
            email='otheruser@example.com',
            password='testpassword123',
            first_name='Other',
            last_name='User'
        )
        
        # Create admin user
        cls.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpassword123'
        )
        
        # Create payment gateway
        cls.gateway = PaymentGateway.objects.create(
            name='paystack',
            is_active=True,
            config={'secret_key': 'test_key', 'public_key': 'test_pub_key'}
        )
        
        # Create wallets
        cls.user_wallet, _ = Wallet.objects.get_or_create(
            user=cls.user,
            defaults={'balance': Decimal('1000.00')}
        )
        
        cls.other_user_wallet, _ = Wallet.objects.get_or_create(
            user=cls.other_user,
            defaults={'balance': Decimal('500.00')}
        )
    
    def setUp(self):
        """Set up for each test method"""
        self.client = Client()
        self.authenticated_client = Client()
        self.authenticated_client.force_login(self.user)
        
        self.admin_client = Client()
        self.admin_client.force_login(self.admin_user)
        
        # Common URLs
        self.fund_url = reverse('payments:initiate_funding')
        self.callback_url = reverse('payments:payment_callback')
        self.withdraw_url = reverse('payments:withdraw')
        self.banks_url = reverse('payments:get_banks')
        self.verify_account_url = reverse('payments:verify_account')
        self.webhook_url = reverse('payments:paystack_webhook')
        self.transaction_history_url = reverse('payments:transaction_history')
    
    def create_payment_transaction(
        self, 
        user=None, 
        transaction_type='funding',
        amount='100.00',
        status='pending',
        gateway_reference=None
    ):
        """Helper to create payment transactions"""
        user = user or self.user
        gateway_reference = gateway_reference or f"TEST_{uuid.uuid4().hex[:8]}"
        
        return PaymentTransaction.objects.create(
            user=user,
            gateway=self.gateway,
            transaction_type=transaction_type,
            amount=Decimal(amount),
            currency='NGN',
            gateway_reference=gateway_reference,
            status=status
        )
    
    def create_paystack_transaction(self, payment_transaction, **kwargs):
        """Helper to create paystack transaction details"""
        defaults = {
            'paystack_reference': f"PS_{uuid.uuid4().hex[:8]}",
            'authorization_url': 'https://checkout.paystack.com/test',
            'access_code': 'test_access_code'
        }
        defaults.update(kwargs)
        
        return PaystackTransaction.objects.create(
            transaction=payment_transaction,
            **defaults
        )
    
    def create_webhook_event(self, reference, event_type='charge.success', processed=False):
        """Helper to create webhook events"""
        return WebhookEvent.objects.create(
            gateway=self.gateway,
            reference=reference,
            event_type=event_type,
            payload={'data': {'reference': reference}},
            processed=processed
        )


class PaystackMockMixin:
    """Mixin providing common Paystack API mocks"""
    
    def mock_paystack_initialize_success(self):
        """Mock successful payment initialization"""
        return {
            'status': True,
            'message': 'Authorization URL created',
            'data': {
                'authorization_url': 'https://checkout.paystack.com/test123',
                'access_code': 'test_access_code',
                'reference': 'test_reference_123'
            }
        }
    
    def mock_paystack_initialize_failure(self):
        """Mock failed payment initialization"""
        return {
            'status': False,
            'message': 'Invalid email address',
            'data': None
        }
    
    def mock_paystack_verify_success(self):
        """Mock successful payment verification"""
        return {
            'status': True,
            'message': 'Verification successful',
            'data': {
                'status': 'success',
                'reference': 'test_reference_123',
                'amount': 10000,  # in kobo
                'gateway_response': 'Successful',
                'paid_at': '2023-01-01T00:00:00.000Z'
            }
        }
    
    def mock_paystack_verify_failure(self):
        """Mock failed payment verification"""
        return {
            'status': False,
            'message': 'Transaction not found',
            'data': None
        }
    
    def mock_banks_response(self):
        """Mock banks list response"""
        return {
            'status': True,
            'message': 'Banks retrieved',
            'data': [
                {'name': 'Access Bank', 'code': '044', 'active': True},
                {'name': 'First Bank', 'code': '011', 'active': True},
                {'name': 'GTB', 'code': '058', 'active': True}
            ]
        }
    
    def mock_account_resolve_success(self):
        """Mock successful account resolution"""
        return {
            'status': True,
            'message': 'Account number resolved',
            'data': {
                'account_number': '1234567890',
                'account_name': 'John Doe',
                'bank_id': 1
            }
        }
    
    def mock_account_resolve_failure(self):
        """Mock failed account resolution"""
        return {
            'status': False,
            'message': 'Could not resolve account name',
            'data': None
        }
    
    def mock_transfer_recipient_success(self):
        """Mock successful transfer recipient creation"""
        return {
            'status': True,
            'message': 'Transfer recipient created successfully',
            'data': {
                'recipient_code': 'RCP_test123',
                'type': 'nuban',
                'name': 'John Doe',
                'account_number': '1234567890',
                'bank_code': '044',
                'currency': 'NGN'
            }
        }
    
    def mock_transfer_initiate_success(self):
        """Mock successful transfer initiation"""
        return {
            'status': True,
            'message': 'Transfer has been queued',
            'data': {
                'transfer_code': 'TRF_test123',
                'reference': 'WD_test123',
                'status': 'pending',
                'amount': 10000
            }
        }


class WalletServiceMockMixin:
    """Mixin for mocking wallet service operations"""
    
    def mock_wallet_service_credit_success(self):
        """Mock successful wallet credit"""
        return {
            'success': True,
            'message': 'Wallet credited successfully',
            'transaction': Mock(id=uuid.uuid4(), amount=Decimal('100.00'))
        }
    
    def mock_wallet_service_debit_success(self):
        """Mock successful wallet debit"""
        return {
            'success': True,
            'message': 'Wallet debited successfully',
            'transaction': Mock(id=uuid.uuid4(), amount=Decimal('100.00'))
        }
    
    def mock_wallet_service_debit_failure(self):
        """Mock failed wallet debit (insufficient balance)"""
        return {
            'success': False,
            'error': 'Insufficient balance',
            'transaction': None
        }


class AuthenticationMixin:
    """Mixin for authentication-related test helpers"""
    
    def assert_login_required(self, url, method='GET', data=None):
        """Assert that a URL requires authentication"""
        if method == 'GET':
            response = self.client.get(url)
        elif method == 'POST':
            response = self.client.post(url, data or {})
        elif method == 'PUT':
            response = self.client.put(url, data or {})
        elif method == 'DELETE':
            response = self.client.delete(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def assert_permission_denied(self, url, method='GET', data=None, user=None):
        """Assert that a user doesn't have permission for a URL"""
        client = Client()
        if user:
            client.force_login(user)
        
        if method == 'GET':
            response = client.get(url)
        elif method == 'POST':
            response = client.post(url, data or {})
        
        self.assertIn(response.status_code, [403, 404])


class JSONResponseMixin:
    """Mixin for JSON response testing helpers"""
    
    def assertJSONSuccess(self, response, expected_keys=None):
        """Assert JSON response is successful"""
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['content-type'], 'application/json')
        
        data = response.json()
        if expected_keys:
            for key in expected_keys:
                self.assertIn(key, data)
    
    def assertJSONError(self, response, expected_error=None, status_code=400):
        """Assert JSON response contains error"""
        self.assertEqual(response.status_code, status_code)
        self.assertEqual(response['content-type'], 'application/json')
        
        data = response.json()
        self.assertIn('success', data)
        self.assertFalse(data['success'])
        
        if expected_error:
            self.assertIn('error', data)
            self.assertIn(expected_error.lower(), data['error'].lower())


class FormValidationMixin:
    """Mixin for form validation testing helpers"""
    
    def assert_form_error(self, response, form_name, field_name, error_message=None):
        """Assert form has specific field error"""
        self.assertContains(response, 'error')
        form = response.context.get(form_name)
        if form:
            self.assertTrue(form.errors)
            if field_name in form.errors:
                if error_message:
                    self.assertIn(error_message, str(form.errors[field_name]))
    
    def assert_form_valid(self, response, form_name):
        """Assert form is valid"""
        form = response.context.get(form_name)
        if form:
            self.assertFalse(form.errors)