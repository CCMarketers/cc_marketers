# payments/tests/test_funding_views.py
import json
from decimal import Decimal
from unittest.mock import patch, Mock
from django.urls import reverse
from django.contrib import messages
from django.contrib.messages import get_messages

from payments.forms import FundingForm
from payments.models import PaymentTransaction, PaystackTransaction
from .test_base import (
    BaseTestCase, PaystackMockMixin, AuthenticationMixin, 
    FormValidationMixin, JSONResponseMixin
)


class InitiateFundingViewTestCase(
    BaseTestCase, PaystackMockMixin, AuthenticationMixin, FormValidationMixin
):
    """Test cases for initiate_funding view"""
    
    def test_get_funding_form_authenticated(self):
        """Test GET request returns funding form for authenticated user"""
        response = self.authenticated_client.get(self.fund_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fund_wallet.html')
        self.assertIsInstance(response.context['form'], FundingForm)
        self.assertFalse(response.context['form'].is_bound)
    
    def test_get_funding_form_unauthenticated(self):
        """Test GET request redirects to login for unauthenticated user"""
        self.assert_login_required(self.fund_url, method='GET')
    
    @patch('payments.views.PaystackService')
    def test_post_valid_form_successful_payment_init(self, mock_paystack_service):
        """Test POST with valid form and successful Paystack initialization"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.initialize_payment.return_value = {
            'success': True,
            'data': {
                'authorization_url': 'https://checkout.paystack.com/test123',
                'access_code': 'test_access_code',
                'reference': 'test_reference_123'
            }
        }
        
        form_data = {
            'amount': '500.00',
            'description': 'Test funding'
        }
        
        response = self.authenticated_client.post(self.fund_url, data=form_data)
        
        # Assert redirect to Paystack
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.paystack.com/test123')
        
        # Verify service was called with correct parameters
        mock_service.initialize_payment.assert_called_once()
        call_args = mock_service.initialize_payment.call_args
        self.assertEqual(call_args[1]['user'], self.user)
        self.assertEqual(call_args[1]['amount'], Decimal('500.00'))
        self.assertIn('payment_callback', call_args[1]['callback_url'])
    
    @patch('payments.views.PaystackService')
    def test_post_valid_form_failed_payment_init(self, mock_paystack_service):
        """Test POST with valid form but failed Paystack initialization"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.initialize_payment.return_value = {
            'success': False,
            'error': 'Invalid email address'
        }
        
        form_data = {
            'amount': '500.00',
            'description': 'Test funding'
        }
        
        response = self.authenticated_client.post(self.fund_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fund_wallet.html')
        
        # Check error message
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Payment initialization failed' in str(m) for m in messages_list))
    
    @patch('payments.views.PaystackService')
    def test_post_valid_form_no_authorization_url(self, mock_paystack_service):
        """Test POST when Paystack returns success but no authorization URL"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.initialize_payment.return_value = {
            'success': True,
            'data': {
                'access_code': 'test_access_code',
                'reference': 'test_reference_123'
                # Missing authorization_url
            }
        }
        
        form_data = {
            'amount': '500.00',
            'description': 'Test funding'
        }
        
        response = self.authenticated_client.post(self.fund_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fund_wallet.html')
        
        # Check specific error message
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('no authorization URL was returned' in str(m) for m in messages_list)
        )
    
    def test_post_invalid_form_amount_too_low(self):
        """Test POST with invalid form data (amount too low)"""
        form_data = {
            'amount': '50.00',  # Below minimum
            'description': 'Test funding'
        }
        
        response = self.authenticated_client.post(self.fund_url, data=form_data)
        
        # Assert re-renders form with validation errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fund_wallet.html')
        self.assert_form_error(response, 'form', 'amount', 'Minimum funding amount')
    
    def test_post_invalid_form_amount_too_high(self):
        """Test POST with invalid form data (amount too high)"""
        form_data = {
            'amount': '2000000.00',  # Above maximum
            'description': 'Test funding'
        }
        
        response = self.authenticated_client.post(self.fund_url, data=form_data)
        
        # Assert re-renders form with validation errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fund_wallet.html')
        self.assert_form_error(response, 'form', 'amount', 'Maximum funding amount')
    
    def test_post_invalid_form_missing_amount(self):
        """Test POST with missing required amount field"""
        form_data = {
            'description': 'Test funding'
            # Missing amount
        }
        
        response = self.authenticated_client.post(self.fund_url, data=form_data)
        
        # Assert re-renders form with validation errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fund_wallet.html')
        self.assert_form_error(response, 'form', 'amount')
    
    def test_post_unauthenticated(self):
        """Test POST request redirects to login for unauthenticated user"""
        form_data = {
            'amount': '500.00',
            'description': 'Test funding'
        }
        
        self.assert_login_required(self.fund_url, method='POST', data=form_data)
    
    @patch('payments.views.PaystackService')
    def test_post_paystack_service_exception(self, mock_paystack_service):
        """Test POST when PaystackService raises an exception"""
        # Setup mock to raise exception
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.initialize_payment.side_effect = Exception("Network error")
        
        form_data = {
            'amount': '500.00',
            'description': 'Test funding'
        }
        
        response = self.authenticated_client.post(self.fund_url, data=form_data)
        
        # Should handle gracefully and show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fund_wallet.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Payment initialization failed' in str(m) for m in messages_list))


class PaymentCallbackViewTestCase(BaseTestCase, AuthenticationMixin):
    """Test cases for payment_callback view"""
    
    def setUp(self):
        super().setUp()
        self.transaction = self.create_payment_transaction(
            user=self.user,
            gateway_reference='TEST_REF_123'
        )
        self.paystack_details = self.create_paystack_transaction(
            self.transaction,
            paystack_reference='PS_REF_123'
        )
    
    def test_get_callback_unauthenticated(self):
        """Test callback redirects to login for unauthenticated user"""
        self.assert_login_required(
            f"{self.callback_url}?reference=TEST_REF_123",
            method='GET'
        )
    
    def test_get_callback_missing_reference(self):
        """Test callback with missing reference parameter"""
        response = self.authenticated_client.get(self.callback_url)
        
        # Should redirect to dashboard with error message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Invalid payment reference' in str(m) for m in messages_list))
    
    @patch('payments.views.PaystackService')
    def test_get_callback_successful_verification(self, mock_paystack_service):
        """Test callback with successful payment verification"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.verify_payment.return_value = {
            'success': True,
            'data': {
                'data': {
                    'status': 'success',
                    'reference': 'TEST_REF_123',
                    'amount': 50000  # 500.00 in kobo
                }
            }
        }
        
        response = self.authenticated_client.get(
            f"{self.callback_url}?reference=TEST_REF_123"
        )
        
        # Should redirect to dashboard with success message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('Payment successful' in str(m) for m in messages_list)
        )
        
        # Verify service was called
        mock_service.verify_payment.assert_called_once_with('TEST_REF_123')
    
    @patch('payments.views.PaystackService')
    def test_get_callback_failed_verification(self, mock_paystack_service):
        """Test callback with failed payment verification"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.verify_payment.return_value = {
            'success': False,
            'data': {
                'data': {
                    'status': 'failed',
                    'reference': 'TEST_REF_123'
                }
            }
        }
        
        response = self.authenticated_client.get(
            f"{self.callback_url}?reference=TEST_REF_123"
        )
        
        # Should redirect to dashboard with error message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('Payment verification failed' in str(m) for m in messages_list)
        )
    
    def test_get_callback_transaction_not_found(self):
        """Test callback with non-existent transaction reference"""
        response = self.authenticated_client.get(
            f"{self.callback_url}?reference=NON_EXISTENT_REF"
        )
        
        # Should redirect to dashboard with error message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Transaction not found' in str(m) for m in messages_list))
    
    def test_get_callback_other_users_transaction(self):
        """Test callback with another user's transaction reference"""
        # Create transaction for other user
        other_transaction = self.create_payment_transaction(
            user=self.other_user,
            gateway_reference='OTHER_USER_REF'
        )
        
        response = self.authenticated_client.get(
            f"{self.callback_url}?reference=OTHER_USER_REF"
        )
        
        # Should redirect to dashboard with error message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Transaction not found' in str(m) for m in messages_list))
    
    @patch('payments.views.PaystackService')
    def test_get_callback_service_exception(self, mock_paystack_service):
        """Test callback when PaystackService raises an exception"""
        # Setup mock to raise exception
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.verify_payment.side_effect = Exception("Network error")
        
        response = self.authenticated_client.get(
            f"{self.callback_url}?reference=TEST_REF_123"
        )
        
        # Should redirect to dashboard with generic error message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('An error occurred during payment verification' in str(m) for m in messages_list)
        )
    
    @patch('payments.views.PaystackService')
    def test_get_callback_verification_returns_none(self, mock_paystack_service):
        """Test callback when verification returns None/empty response"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.verify_payment.return_value = {
            'success': True,
            'data': None  # Empty data
        }
        
        response = self.authenticated_client.get(
            f"{self.callback_url}?reference=TEST_REF_123"
        )
        
        # Should redirect to dashboard with error message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('Payment verification failed' in str(m) for m in messages_list)
        )