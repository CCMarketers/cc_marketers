# payments/tests/test_integration.py
"""
Integration tests for the payments app

These tests verify that all components work together correctly in realistic scenarios.
"""

import json
from decimal import Decimal
from unittest.mock import patch, Mock
from django.test import TransactionTestCase
from django.urls import reverse
from django.contrib.messages import get_messages

from payments.models import PaymentTransaction, PaystackTransaction, WebhookEvent
from payments.services import PaystackService, WebhookService
from .test_base import BaseTestCase, PaystackMockMixin, WalletServiceMockMixin


class PaymentIntegrationTestCase(BaseTestCase, PaystackMockMixin, WalletServiceMockMixin):
    """End-to-end integration tests for payment flows"""
    
    @patch('wallets.services.WalletService.credit_wallet')
    @patch('payments.services.requests.get')
    @patch('payments.services.requests.post')
    def test_complete_funding_flow(self, mock_post, mock_get, mock_credit):
        """Test complete funding flow from initiation to webhook processing"""
        
        # Setup mocks
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = self.mock_paystack_initialize_success()
        
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = self.mock_paystack_verify_success()
        
        mock_credit.return_value = self.mock_wallet_service_credit_success()
        
        # Step 1: Initiate funding
        form_data = {
            'amount': '500.00',
            'description': 'Integration test funding'
        }
        
        response = self.authenticated_client.post(
            reverse('payments:initiate_funding'),
            data=form_data
        )
        
        # Should redirect to Paystack
        self.assertEqual(response.status_code, 302)
        self.assertIn('checkout.paystack.com', response.url)
        
        # Verify transaction was created
        transaction = PaymentTransaction.objects.get(user=self.user)
        self.assertEqual(transaction.amount, Decimal('500.00'))
        self.assertEqual(transaction.status, 'pending')
        
        # Step 2: Handle callback (user returns from Paystack)
        callback_response = self.authenticated_client.get(
            f"{reverse('payments:payment_callback')}?reference={transaction.gateway_reference}"
        )
        
        # Should redirect to dashboard with success message
        self.assertRedirects(callback_response, reverse('wallets:dashboard'))
        
        # Step 3: Process webhook (Paystack notifies us)
        webhook_payload = {
            'event': 'charge.success',
            'data': {
                'reference': transaction.gateway_reference,
                'amount': 50000,  # 500.00 in kobo
                'status': 'success'
            }
        }
        
        # Generate valid signature
        import hmac
        import hashlib
        from django.conf import settings
        
        webhook_json = json.dumps(webhook_payload).encode('utf-8')
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', 'test_secret')
        signature = hmac.new(
            secret_key.encode('utf-8'),
            webhook_json,
            hashlib.sha512
        ).hexdigest()
        
        webhook_response = self.client.post(
            reverse('payments:paystack_webhook'),
            data=webhook_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(webhook_response.status_code, 200)
        
        # Verify final state
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, 'success')
        self.assertIsNotNone(transaction.completed_at)
        
        # Verify wallet was credited
        mock_credit.assert_called_once()
        
        # Verify webhook event was processed
        webhook_event = WebhookEvent.objects.get(reference=transaction.gateway_reference)
        self.assertTrue(webhook_event.processed)
        self.assertIsNotNone(webhook_event.processed_at)
    
    @patch('wallets.services.WalletService.credit_wallet')
    @patch('wallets.services.WalletService.debit_wallet')
    @patch('payments.services.requests.get')
    @patch('payments.services.requests.post')
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_complete_withdrawal_flow(self, mock_get_wallet, mock_post, mock_get, mock_debit, mock_credit):
        """Test complete withdrawal flow from initiation to webhook processing"""
        
        # Setup mocks
        mock_get_wallet.return_value = Decimal('1000.00')
        mock_debit.return_value = self.mock_wallet_service_debit_success()
        mock_credit.return_value = self.mock_wallet_service_credit_success()
        
        # Mock account verification
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = self.mock_account_resolve_success()
        
        # Mock recipient creation and transfer initiation
        mock_post.side_effect = [
            # First call: create recipient
            Mock(status_code=201, json=lambda: self.mock_transfer_recipient_success()),
            # Second call: initiate transfer
            Mock(status_code=200, json=lambda: self.mock_transfer_initiate_success())
        ]
        
        # Step 1: Initiate withdrawal
        form_data = {
            'amount': '300.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(
            reverse('payments:withdraw'),
            data=form_data
        )
        
        # Should redirect to dashboard with success message
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any('Withdrawal of ₦300.00' in str(m) and 'initiated successfully' in str(m)
                for m in messages_list)
        )
        
        # Verify transaction was created
        transaction = PaymentTransaction.objects.get(
            user=self.user,
            transaction_type='withdrawal'
        )
        self.assertEqual(transaction.amount, Decimal('300.00'))
        self.assertEqual(transaction.status, 'pending')
        
        # Verify wallet was debited
        mock_debit.assert_called_once()
        
        # Step 2: Process successful transfer webhook
        webhook_payload = {
            'event': 'transfer.success',
            'data': {
                'reference': transaction.gateway_reference,
                'amount': 30000,  # 300.00 in kobo
                'status': 'success'
            }
        }
        
        webhook_json = json.dumps(webhook_payload).encode('utf-8')
        
        # Generate valid signature
        import hmac
        import hashlib
        from django.conf import settings
        
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', 'test_secret')
        signature = hmac.new(
            secret_key.encode('utf-8'),
            webhook_json,
            hashlib.sha512
        ).hexdigest()
        
        webhook_response = self.client.post(
            reverse('payments:paystack_webhook'),
            data=webhook_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(webhook_response.status_code, 200)
        
        # Verify final state
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, 'success')
        self.assertIsNotNone(transaction.completed_at)
        
        # Verify webhook event was processed
        webhook_event = WebhookEvent.objects.get(reference=transaction.gateway_reference)
        self.assertTrue(webhook_event.processed)
    
    @patch('wallets.services.WalletService.credit_wallet')
    @patch('wallets.services.WalletService.debit_wallet')
    @patch('payments.services.requests.get')
    @patch('payments.services.requests.post')
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def test_failed_withdrawal_with_refund(self, mock_get_wallet, mock_post, mock_get, mock_debit, mock_credit):
        """Test withdrawal flow when transfer fails and wallet is refunded"""
        
        # Setup mocks
        mock_get_wallet.return_value = Decimal('1000.00')
        mock_debit.return_value = self.mock_wallet_service_debit_success()
        mock_credit.return_value = self.mock_wallet_service_credit_success()
        
        # Mock account verification
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = self.mock_account_resolve_success()
        
        # Mock recipient creation and transfer initiation
        mock_post.side_effect = [
            # First call: create recipient
            Mock(status_code=201, json=lambda: self.mock_transfer_recipient_success()),
            # Second call: initiate transfer
            Mock(status_code=200, json=lambda: self.mock_transfer_initiate_success())
        ]
        
        # Step 1: Initiate withdrawal
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        response = self.authenticated_client.post(
            reverse('payments:withdraw'),
            data=form_data
        )
        
        self.assertRedirects(response, reverse('wallets:dashboard'))
        
        # Get the created transaction
        transaction = PaymentTransaction.objects.get(
            user=self.user,
            transaction_type='withdrawal'
        )
        
        # Step 2: Process failed transfer webhook
        webhook_payload = {
            'event': 'transfer.failed',
            'data': {
                'reference': transaction.gateway_reference,
                'amount': 20000,  # 200.00 in kobo
                'status': 'failed'
            }
        }
        
        webhook_json = json.dumps(webhook_payload).encode('utf-8')
        
        # Generate valid signature
        import hmac
        import hashlib
        from django.conf import settings
        
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', 'test_secret')
        signature = hmac.new(
            secret_key.encode('utf-8'),
            webhook_json,
            hashlib.sha512
        ).hexdigest()
        
        webhook_response = self.client.post(
            reverse('payments:paystack_webhook'),
            data=webhook_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(webhook_response.status_code, 200)
        
        # Verify transaction was marked as failed
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, 'failed')
        
        # Verify wallet was refunded
        self.assertEqual(mock_credit.call_count, 1)
        refund_call = mock_credit.call_args
        self.assertEqual(refund_call[1]['user'], self.user)
        self.assertEqual(refund_call[1]['amount'], Decimal('200.00'))
        self.assertEqual(refund_call[1]['category'], 'withdrawal_refund')
    
    def test_transaction_history_integration(self):
        """Test transaction history view with multiple transactions"""
        
        # Create multiple transactions
        transactions = []
        for i in range(3):
            transaction = self.create_payment_transaction(
                user=self.user,
                transaction_type='funding' if i % 2 == 0 else 'withdrawal',
                amount=f'{100 + i * 50}.00',
                status='success' if i < 2 else 'pending',
                gateway_reference=f'HISTORY_REF_{i}'
            )
            transactions.append(transaction)
        
        # Access transaction history
        response = self.authenticated_client.get(reverse('payments:transaction_history'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'transaction_history.html')
        
        # Verify all transactions are displayed
        context_transactions = response.context['transactions']
        self.assertEqual(len(context_transactions), 3)
        
        # Verify ordering (most recent first)
        transaction_ids = [t.id for t in context_transactions]
        expected_ids = [t.id for t in reversed(transactions)]  # Reverse order
        self.assertEqual(transaction_ids, expected_ids)
    
    def test_transaction_detail_integration(self):
        """Test transaction detail view with Paystack details"""
        
        # Create transaction with Paystack details
        transaction = self.create_payment_transaction(
            user=self.user,
            transaction_type='funding',
            amount='750.00',
            status='success',
            gateway_reference='DETAIL_REF_001'
        )
        
        paystack_details = self.create_paystack_transaction(
            transaction,
            paystack_reference='PS_DETAIL_REF',
            authorization_url='https://checkout.paystack.com/detail_test',
            access_code='detail_access_code'
        )
        
        # Access transaction detail
        response = self.authenticated_client.get(
            reverse('payments:transaction_detail', kwargs={'transaction_id': transaction.id})
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'transaction_detail.html')
        
        # Verify transaction and Paystack details are accessible
        context_transaction = response.context['transaction']
        self.assertEqual(context_transaction.id, transaction.id)
        self.assertEqual(context_transaction.amount, Decimal('750.00'))
        
        # Verify Paystack details are included
        self.assertTrue(hasattr(context_transaction, 'paystack_details'))
        self.assertEqual(
            context_transaction.paystack_details.paystack_reference,
            'PS_DETAIL_REF'
        )
    
    @patch('payments.services.requests.get')
    def test_api_integration(self, mock_get):
        """Test API endpoints integration"""
        
        # Test banks API
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = self.mock_banks_response()
        
        banks_response = self.authenticated_client.get(reverse('payments:get_banks'))
        
        self.assertEqual(banks_response.status_code, 200)
        banks_data = banks_response.json()
        self.assertIn('banks', banks_data)
        self.assertEqual(len(banks_data['banks']), 3)
        
        # Test account verification API
        mock_get.return_value.json.return_value = self.mock_account_resolve_success()
        
        verify_data = {
            'account_number': '1234567890',
            'bank_code': '044'
        }
        
        verify_response = self.authenticated_client.post(
            reverse('payments:verify_account'),
            data=json.dumps(verify_data),
            content_type='application/json'
        )
        
        self.assertEqual(verify_response.status_code, 200)
        verify_result = verify_response.json()
        self.assertTrue(verify_result['success'])
        self.assertEqual(verify_result['account_name'], 'John Doe')


class PerformanceIntegrationTestCase(TransactionTestCase):
    """Integration tests focused on performance and database queries"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        cls.user = User.objects.create_user(
            username='perfuser',
            email='perfuser@example.com',
            password='testpass123'
        )
        
        from payments.models import PaymentGateway
        cls.gateway = PaymentGateway.objects.create(name='paystack', is_active=True)
    
    def setUp(self):
        super().setUp()
        from django.test import Client
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_transaction_history_query_optimization(self):
        """Test that transaction history doesn't cause N+1 query problems"""
        
        # Create many transactions
        from payments.models import PaymentTransaction
        transactions = []
        for i in range(20):
            transaction = PaymentTransaction.objects.create(
                user=self.user,
                gateway=self.gateway,
                transaction_type='funding',
                amount=f'{100 + i}.00',
                gateway_reference=f'PERF_REF_{i}'
            )
            transactions.append(transaction)
        
        # Test query count for transaction history
        with self.assertNumQueries(1):  # Should only be 1 query due to select_related
            response = self.client.get(reverse('payments:transaction_history'))
            
            # Access all transactions and their gateways (should not cause additional queries)
            for transaction in response.context['transactions']:
                gateway_name = transaction.gateway.name
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['transactions']), 20)