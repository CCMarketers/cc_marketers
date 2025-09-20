# payments/tests/test_withdrawal_views.py
from decimal import Decimal
from unittest.mock import patch, Mock
from django.urls import reverse
from django.contrib.messages import get_messages

from payments.forms import WithdrawalForm
from payments.models import PaymentTransaction
from .test_base import (
    BaseTestCase, PaystackMockMixin, WalletServiceMockMixin,
    AuthenticationMixin, FormValidationMixin
)


class WithdrawFundsViewTestCase(
    BaseTestCase, PaystackMockMixin, WalletServiceMockMixin, 
    AuthenticationMixin, FormValidationMixin
):
    """Test cases for withdraw_funds view"""
    
    def test_get_withdrawal_form_authenticated(self):
        """Test GET request returns withdrawal form for authenticated user"""
        response = self.authenticated_client.get(self.withdraw_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        self.assertIsInstance(response.context['form'], WithdrawalForm)
        self.assertFalse(response.context['form'].is_bound)
    
    def test_get_withdrawal_form_unauthenticated(self):
        """Test GET request redirects to login for unauthenticated user"""
        self.assert_login_required(self.withdraw_url, method='GET')
    
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_insufficient_balance(self, mock_get_wallet):
        """Test POST with withdrawal amount exceeding wallet balance"""
        # Mock wallet balance lower than withdrawal amount
        mock_get_wallet.return_value = Decimal('50.00')
        
        form_data = {
            'amount': '100.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Insufficient wallet balance' in str(m) for m in messages_list))
    
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_below_minimum_withdrawal(self, mock_get_wallet):
        """Test POST with withdrawal amount below minimum"""
        mock_get_wallet.return_value = Decimal('1000.00')
        
        form_data = {
            'amount': '50.00',  # Below minimum of 100
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Minimum withdrawal amount is ₦100' in str(m) for m in messages_list))
    
    @patch('payments.views.PaystackService')
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_invalid_account_details(self, mock_get_wallet, mock_paystack_service):
        """Test POST with invalid bank account details"""
        mock_get_wallet.return_value = Decimal('1000.00')
        
        # Setup mock for account verification failure
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = {
            'status': False,
            'message': 'Could not resolve account name'
        }
        
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '9999999999'  # Invalid account
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Invalid account details' in str(m) for m in messages_list))
    
    @patch('wallets.services.WalletService.debit_wallet')
    @patch('payments.views.PaystackService')
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_failed_recipient_creation(self, mock_get_wallet, mock_paystack_service, mock_debit):
        """Test POST when Paystack fails to create transfer recipient"""
        mock_get_wallet.return_value = Decimal('1000.00')
        
        # Setup mocks
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = self.mock_account_resolve_success()
        mock_service.create_transfer_recipient.return_value = {
            'status': False,
            'message': 'Invalid bank code'
        }
        
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Failed to create transfer recipient' in str(m) for m in messages_list))
    
    @patch('wallets.services.WalletService.debit_wallet')
    @patch('payments.views.PaystackService')
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_failed_wallet_debit(self, mock_get_wallet, mock_paystack_service, mock_debit):
        """Test POST when wallet debit fails"""
        mock_get_wallet.return_value = Decimal('1000.00')
        mock_debit.return_value = self.mock_wallet_service_debit_failure()
        
        # Setup mocks
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = self.mock_account_resolve_success()
        mock_service.create_transfer_recipient.return_value = self.mock_transfer_recipient_success()
        
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Failed to debit wallet' in str(m) for m in messages_list))
    
    @patch('wallets.services.WalletService.credit_wallet')
    @patch('wallets.services.WalletService.debit_wallet')
    @patch('payments.views.PaystackService')
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_failed_transfer_initiation_with_refund(
        self, mock_get_wallet, mock_paystack_service, mock_debit, mock_credit
    ):
        """Test POST when transfer initiation fails and wallet is refunded"""
        mock_get_wallet.return_value = Decimal('1000.00')
        mock_debit.return_value = self.mock_wallet_service_debit_success()
        mock_credit.return_value = self.mock_wallet_service_credit_success()
        
        # Setup mocks
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = self.mock_account_resolve_success()
        mock_service.create_transfer_recipient.return_value = self.mock_transfer_recipient_success()
        mock_service.initiate_transfer.return_value = {
            'success': False,
            'error': 'Insufficient funds in Paystack account'
        }
        
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert re-renders form with error message
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Withdrawal failed' in str(m) for m in messages_list))
        
        # Verify wallet was refunded
        mock_credit.assert_called_once_with(
            self.user, Decimal('200.00'), "Refund for failed withdrawal"
        )
    
    @patch('wallets.services.WalletService.debit_wallet')
    @patch('payments.views.PaystackService')
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_successful_withdrawal(self, mock_get_wallet, mock_paystack_service, mock_debit):
        """Test POST with successful withdrawal initiation"""
        mock_get_wallet.return_value = Decimal('1000.00')
        mock_debit.return_value = self.mock_wallet_service_debit_success()
        
        # Setup mocks
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = self.mock_account_resolve_success()
        mock_service.create_transfer_recipient.return_value = self.mock_transfer_recipient_success()
        mock_service.initiate_transfer.return_value = {
            'success': True,
            'data': {
                'transfer_code': 'TRF_test123',
                'reference': 'WD_test123'
            }
        }
        
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert redirects to dashboard with success message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('Withdrawal of ₦200.00' in str(m) and 'initiated successfully' in str(m) 
                for m in messages_list)
        )
        
        # Verify wallet was debited
        mock_debit.assert_called_once()
    
    def test_post_invalid_form_data(self):
        """Test POST with invalid form data"""
        form_data = {
            'amount': 'invalid_amount',
            'bank_code': '',
            'account_number': '123'  # Too short
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Assert re-renders form with validation errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        self.assert_form_error(response, 'form', 'amount')
        self.assert_form_error(response, 'form', 'account_number')
    
    def test_post_unauthenticated(self):
        """Test POST request redirects to login for unauthenticated user"""
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        self.assert_login_required(self.withdraw_url, method='POST', data=form_data)
    
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_post_general_exception(self, mock_get_wallet):
        """Test POST when an unexpected exception occurs"""
        # Mock to raise an exception
        mock_get_wallet.side_effect = Exception("Database error")
        
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(self.withdraw_url, data=form_data)
        
        # Should handle gracefully and show error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'withdraw.html')
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('An error occurred during withdrawal' in str(m) for m in messages_list))