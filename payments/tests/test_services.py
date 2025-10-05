# payments/tests/test_services.py
import json
from decimal import Decimal
from unittest.mock import patch, Mock, MagicMock
from django.test import TestCase
from django.utils import timezone

from payments.services import PaystackService, WebhookService
from payments.models import PaymentTransaction, PaystackTransaction, WebhookEvent
from .test_base import BaseTestCase, PaystackMockMixin


class PaystackServiceTestCase(BaseTestCase, PaystackMockMixin):
    """Test cases for PaystackService"""
    
    def setUp(self):
        super().setUp()
        self.service = PaystackService()
    
    @patch('payments.services.requests.post')
    def test_initialize_payment_success(self, mock_post):
        """Test successful payment initialization"""
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_paystack_initialize_success()
        mock_post.return_value = mock_response
        
        result = self.service.initialize_payment(
            user=self.user,
            amount=Decimal('500.00'),
            callback_url='http://example.com/callback'
        )
        
        self.assertTrue(result['success'])
        self.assertIn('data', result)
        self.assertIn('authorization_url', result['data'])
        self.assertEqual(result['data']['authorization_url'], 'https://checkout.paystack.com/test123')
        
        # Verify database record was created
        self.assertTrue(PaymentTransaction.objects.filter(user=self.user).exists())
        
        # Verify API call was made with correct data
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL
        self.assertIn('/transaction/initialize', call_args[0][0])
        
        # Check request data
        request_data = call_args[1]['json']
        self.assertEqual(request_data['email'], self.user.email)
        self.assertEqual(request_data['amount'], 50000)  # 500.00 * 100 (kobo)
        self.assertEqual(request_data['currency'], 'NGN')
        self.assertIn('callback_url', request_data)
    
    @patch('payments.services.requests.post')
    def test_initialize_payment_api_failure(self, mock_post):
        """Test payment initialization when Paystack API fails"""
        # Setup mock response for failure
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = self.mock_paystack_initialize_failure()
        mock_post.return_value = mock_response
        
        result = self.service.initialize_payment(
            user=self.user,
            amount=Decimal('500.00')
        )
        
        self.assertFalse(result['success'])
        self.assertIn('error', result)
        self.assertEqual(result['error'], 'Invalid email address')
        
        # Verify transaction was marked as failed
        transaction = PaymentTransaction.objects.get(user=self.user)
        self.assertEqual(transaction.status, 'failed')
    
    @patch('payments.services.requests.post')
    def test_initialize_payment_missing_auth_url(self, mock_post):
        """Test when Paystack returns success but missing authorization_url"""
        # Setup mock response without authorization_url
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': True,
            'data': {
                'access_code': 'test_code',
                'reference': 'test_ref'
                # Missing authorization_url
            }
        }
        mock_post.return_value = mock_response
        
        result = self.service.initialize_payment(
            user=self.user,
            amount=Decimal('500.00')
        )
        
        self.assertFalse(result['success'])
        self.assertIn('No authorization_url returned', result['error'])
    
    @patch('payments.services.requests.post')
    def test_initialize_payment_network_error(self, mock_post):
        """Test payment initialization with network error"""
        mock_post.side_effect = Exception('Network timeout')
        
        result = self.service.initialize_payment(
            user=self.user,
            amount=Decimal('500.00')
        )
        
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Network timeout')
    
    @patch('payments.services.requests.get')
    def test_verify_payment_success(self, mock_get):
        """Test successful payment verification"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_paystack_verify_success()
        mock_get.return_value = mock_response
        
        result = self.service.verify_payment('test_reference_123')
        
        self.assertTrue(result['success'])
        self.assertIn('data', result)
        
        # Verify API call
        mock_get.assert_called_once()
        self.assertIn('test_reference_123', mock_get.call_args[0][0])
    
    @patch('payments.services.requests.get')
    def test_verify_payment_failure(self, mock_get):
        """Test failed payment verification"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = self.mock_paystack_verify_failure()
        mock_get.return_value = mock_response
        
        result = self.service.verify_payment('invalid_reference')
        
        self.assertFalse(result['success'])
    
    @patch('payments.services.requests.post')
    def test_create_transfer_recipient_success(self, mock_post):
        """Test successful transfer recipient creation"""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = self.mock_transfer_recipient_success()
        mock_post.return_value = mock_response
        
        result = self.service.create_transfer_recipient(
            user=self.user,
            bank_code='044',
            account_number='1234567890'
        )
        
        self.assertTrue(result['success'])
        self.assertIn('data', result)
        
        # Verify API call
        mock_post.assert_called_once()
        request_data = mock_post.call_args[1]['json']
        self.assertEqual(request_data['bank_code'], '044')
        self.assertEqual(request_data['account_number'], '1234567890')
        self.assertEqual(request_data['type'], 'nuban')
    
    @patch('payments.services.requests.post')
    def test_initiate_transfer_success(self, mock_post):
        """Test successful transfer initiation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_transfer_initiate_success()
        mock_post.return_value = mock_response
        
        result = self.service.initiate_transfer(
            user=self.user,
            amount=Decimal('200.00'),
            recipient_code='RCP_test123'
        )
        
        self.assertTrue(result['success'])
        self.assertIn('transaction', result)
        
        # Verify transaction was created
        transaction = PaymentTransaction.objects.get(
            user=self.user,
            transaction_type='withdrawal'
        )
        self.assertEqual(transaction.amount, Decimal('200.00'))
        self.assertEqual(transaction.status, 'pending')
    
    @patch('payments.services.requests.get')
    def test_get_banks_success(self, mock_get):
        """Test successful banks retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_banks_response()
        mock_get.return_value = mock_response
        
        result = self.service.get_banks()
        
        self.assertTrue(result['success'])
        self.assertIn('data', result)
        self.assertEqual(len(result['data']), 3)
        self.assertEqual(result['data'][0]['name'], 'Access Bank')
    
    @patch('payments.services.requests.get')
    def test_resolve_account_number_success(self, mock_get):
        """Test successful account number resolution"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = self.mock_account_resolve_success()
        mock_get.return_value = mock_response
        
        result = self.service.resolve_account_number('1234567890', '044')
        
        self.assertTrue(result['success'])
        self.assertIn('data', result)
        self.assertEqual(result['data']['account_name'], 'John Doe')
    
    @patch('payments.services.requests.get')
    def test_resolve_account_number_failure(self, mock_get):
        """Test failed account number resolution"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = self.mock_account_resolve_failure()
        mock_get.return_value = mock_response
        
        result = self.service.resolve_account_number('9999999999', '044')
        
        self.assertFalse(result['success'])
        self.assertIn('error', result)


class WebhookServiceTestCase(BaseTestCase):
    """Test cases for WebhookService"""
    
    def setUp(self):
        super().setUp()
        # Create a test payment transaction
        self.transaction = self.create_payment_transaction(
            user=self.user,
            transaction_type='funding',
            amount='100.00',
            gateway_reference='WEBHOOK_TEST_REF',
            status='pending'
        )
    
    def test_verify_paystack_signature_valid(self):
        """Test valid Paystack signature verification"""
        payload = b'{"event": "charge.success"}'
        
        # Generate valid signature
        import hmac
        import hashlib
        from django.conf import settings
        
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', 'test_secret')
        expected_signature = hmac.new(
            secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        result = WebhookService.verify_paystack_signature(payload, expected_signature)
        
        self.assertTrue(result)
    
    def test_verify_paystack_signature_invalid(self):
        """Test invalid Paystack signature verification"""
        payload = b'{"event": "charge.success"}'
        invalid_signature = 'invalid_signature_hash'
        
        result = WebhookService.verify_paystack_signature(payload, invalid_signature)
        
        self.assertFalse(result)
    
    @patch('payments.services.WalletService.credit_wallet')
    def test_handle_successful_charge(self, mock_credit_wallet):
        """Test handling successful charge webhook"""
        mock_credit_wallet.return_value = {
            'success': True,
            'transaction': Mock()
        }
        
        webhook_data = {
            'event': 'charge.success',
            'data': {
                'reference': 'WEBHOOK_TEST_REF',
                'amount': 10000,  # 100.00 in kobo
                'status': 'success'
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertTrue(result['success'])
        
        # Verify transaction was updated
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.status, 'success')
        self.assertIsNotNone(self.transaction.completed_at)
        
        # Verify wallet was credited
        mock_credit_wallet.assert_called_once()
        call_args = mock_credit_wallet.call_args
        self.assertEqual(call_args[1]['user'], self.user)
        self.assertEqual(call_args[1]['amount'], Decimal('100.00'))
        self.assertEqual(call_args[1]['category'], 'funding')
    
    def test_handle_successful_charge_transaction_not_found(self):
        """Test handling charge webhook for non-existent transaction"""
        webhook_data = {
            'event': 'charge.success',
            'data': {
                'reference': 'NON_EXISTENT_REF',
                'amount': 10000,
                'status': 'success'
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertFalse(result['success'])
        self.assertIn('Funding transaction not found', result['error'])
    
    def test_handle_successful_charge_already_processed(self):
        """Test handling charge webhook for already processed transaction"""
        # Mark transaction as already successful
        self.transaction.status = 'success'
        self.transaction.completed_at = timezone.now()
        self.transaction.save()
        
        webhook_data = {
            'event': 'charge.success',
            'data': {
                'reference': 'WEBHOOK_TEST_REF',
                'amount': 10000,
                'status': 'success'
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message'], 'Charge already processed')
    
    @patch('wallets.services.WalletService.credit_wallet')
    def test_handle_successful_transfer(self, mock_credit_wallet):
        """Test handling successful transfer webhook"""
        # Create withdrawal transaction
        withdrawal_transaction = self.create_payment_transaction(
            user=self.user,
            transaction_type='withdrawal',
            amount='150.00',
            gateway_reference='WITHDRAWAL_REF',
            status='pending'
        )
        
        webhook_data = {
            'event': 'transfer.success',
            'data': {
                'reference': 'WITHDRAWAL_REF',
                'amount': 15000,  # 150.00 in kobo
                'status': 'success'
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertTrue(result['success'])
        
        # Verify transaction was updated
        withdrawal_transaction.refresh_from_db()
        self.assertEqual(withdrawal_transaction.status, 'success')
        self.assertIsNotNone(withdrawal_transaction.completed_at)
    
    @patch('wallets.services.WalletService.credit_wallet')
    def test_handle_failed_transfer(self, mock_credit_wallet):
        """Test handling failed transfer webhook"""
        mock_credit_wallet.return_value = {
            'success': True,
            'transaction': Mock()
        }
        
        # Create withdrawal transaction
        withdrawal_transaction = self.create_payment_transaction(
            user=self.user,
            transaction_type='withdrawal',
            amount='150.00',
            gateway_reference='FAILED_WITHDRAWAL_REF',
            status='pending'
        )
        
        webhook_data = {
            'event': 'transfer.failed',
            'data': {
                'reference': 'FAILED_WITHDRAWAL_REF',
                'amount': 15000,
                'status': 'failed'
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertTrue(result['success'])
        
        # Verify transaction was marked as failed
        withdrawal_transaction.refresh_from_db()
        self.assertEqual(withdrawal_transaction.status, 'failed')
        
        # Verify wallet was refunded
        mock_credit_wallet.assert_called_once()
        call_args = mock_credit_wallet.call_args
        self.assertEqual(call_args[1]['user'], self.user)
        self.assertEqual(call_args[1]['amount'], Decimal('150.00'))
        self.assertEqual(call_args[1]['category'], 'withdrawal_refund')
    
    def test_process_webhook_no_reference(self):
        """Test processing webhook with no reference"""
        webhook_data = {
            'event': 'charge.success',
            'data': {
                'amount': 10000,
                'status': 'success'
                # Missing reference
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'No reference found')
    
    def test_process_webhook_duplicate_event(self):
        """Test processing duplicate webhook event"""
        # Create webhook event
        webhook_event = self.create_webhook_event(
            reference='WEBHOOK_TEST_REF',
            event_type='charge.success',
            processed=True
        )
        
        webhook_data = {
            'event': 'charge.success',
            'data': {
                'reference': 'WEBHOOK_TEST_REF',
                'amount': 10000,
                'status': 'success'
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message'], 'Duplicate event ignored')
    
    def test_process_webhook_unhandled_event(self):
        """Test processing unhandled webhook event type"""
        webhook_data = {
            'event': 'subscription.create',  # Unhandled event type
            'data': {
                'reference': 'WEBHOOK_TEST_REF',
                'status': 'active'
            }
        }
        
        result = WebhookService.process_paystack_webhook(webhook_data)
        
        self.assertTrue(result['success'])
        self.assertEqual(result['message'], 'Unhandled event recorded')
        
        # Verify webhook event was created and marked as 'other'
        webhook_event = WebhookEvent.objects.get(reference='WEBHOOK_TEST_REF')
        self.assertEqual(webhook_event.event_type, 'other')
    
    def test_process_webhook_exception_handling(self):
        """Test webhook processing with exception in handler"""
        # Create transaction that will cause an exception (e.g., database constraint)
        with patch('payments.models.PaymentTransaction.objects.select_for_update') as mock_select:
            mock_select.side_effect = Exception('Database error')
            
            webhook_data = {
                'event': 'charge.success',
                'data': {
                    'reference': 'WEBHOOK_TEST_REF',
                    'amount': 10000,
                    'status': 'success'
                }
            }
            
            result = WebhookService.process_paystack_webhook(webhook_data)
            
            self.assertFalse(result['success'])
            self.assertEqual(result['error'], 'Database error')