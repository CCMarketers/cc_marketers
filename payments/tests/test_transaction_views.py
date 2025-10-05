# payments/tests/test_transaction_views.py
import uuid
from django.urls import reverse
from django.http import Http404

from payments.models import PaymentTransaction
from .test_base import BaseTestCase, AuthenticationMixin


class TransactionHistoryViewTestCase(BaseTestCase, AuthenticationMixin):
    """Test cases for transaction_history view"""
    
    def setUp(self):
        super().setUp()
        # Create multiple transactions for the user
        self.user_transactions = []
        for i in range(5):
            transaction = self.create_payment_transaction(
                user=self.user,
                transaction_type='funding' if i % 2 == 0 else 'withdrawal',
                amount=f'{100 + i * 50}.00',
                gateway_reference=f'USER_REF_{i}'
            )
            self.user_transactions.append(transaction)
        
        # Create transactions for other user (should not appear)
        self.other_user_transactions = []
        for i in range(3):
            transaction = self.create_payment_transaction(
                user=self.other_user,
                transaction_type='funding',
                amount=f'{200 + i * 25}.00',
                gateway_reference=f'OTHER_REF_{i}'
            )
            self.other_user_transactions.append(transaction)
    
    def test_transaction_history_unauthenticated(self):
        """Test transaction history requires authentication"""
        self.assert_login_required(self.transaction_history_url, method='GET')
    
    def test_transaction_history_authenticated(self):
        """Test transaction history for authenticated user"""
        response = self.authenticated_client.get(self.transaction_history_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'transaction_history.html')
        
        # Check that only user's transactions are displayed
        transactions = response.context['transactions']
        self.assertEqual(len(transactions), 5)
        
        # Verify all transactions belong to the user
        for transaction in transactions:
            self.assertEqual(transaction.user, self.user)
        
        # Verify transactions are ordered by created_at (descending)
        transaction_dates = [t.created_at for t in transactions]
        self.assertEqual(transaction_dates, sorted(transaction_dates, reverse=True))
    
    def test_transaction_history_empty(self):
        """Test transaction history when user has no transactions"""
        # Delete all user transactions
        PaymentTransaction.objects.filter(user=self.user).delete()
        
        response = self.authenticated_client.get(self.transaction_history_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'transaction_history.html')
        
        transactions = response.context['transactions']
        self.assertEqual(len(transactions), 0)
    
    def test_transaction_history_excludes_other_users(self):
        """Test that transaction history doesn't show other users' transactions"""
        response = self.authenticated_client.get(self.transaction_history_url)
        
        transactions = response.context['transactions']
        
        # Verify no other user's transactions are included
        for transaction in transactions:
            self.assertNotEqual(transaction.user, self.other_user)
    
    def test_transaction_history_contains_required_data(self):
        """Test that transaction history contains all required transaction data"""
        response = self.authenticated_client.get(self.transaction_history_url)
        
        transactions = response.context['transactions']
        
        for transaction in transactions:
            # Verify essential fields are present
            self.assertIsNotNone(transaction.transaction_type)
            self.assertIsNotNone(transaction.amount)
            self.assertIsNotNone(transaction.currency)
            self.assertIsNotNone(transaction.status)
            self.assertIsNotNone(transaction.gateway_reference)
            self.assertIsNotNone(transaction.created_at)
    
    def test_transaction_history_select_related(self):
        """Test that transaction history uses select_related for efficiency"""
        # This test ensures the view is optimized to avoid N+1 queries
        with self.assertNumQueries(1):  # Should only make 1 query due to select_related
            response = self.authenticated_client.get(self.transaction_history_url)
            transactions = list(response.context['transactions'])
            
            # Access related gateway field (should not trigger additional queries)
            for transaction in transactions:
                gateway_name = transaction.gateway.name


class TransactionDetailViewTestCase(BaseTestCase, AuthenticationMixin):
    """Test cases for transaction_detail view"""
    
    def setUp(self):
        super().setUp()
        # Create a transaction for the user
        self.user_transaction = self.create_payment_transaction(
            user=self.user,
            transaction_type='funding',
            amount='150.00',
            status='success',
            gateway_reference='USER_DETAIL_REF'
        )
        
        # Create Paystack details for the transaction
        self.paystack_details = self.create_paystack_transaction(
            self.user_transaction,
            paystack_reference='PS_DETAIL_REF',
            authorization_url='https://checkout.paystack.com/detail_test'
        )
        
        # Create a transaction for other user
        self.other_user_transaction = self.create_payment_transaction(
            user=self.other_user,
            transaction_type='withdrawal',
            amount='75.00',
            gateway_reference='OTHER_DETAIL_REF'
        )
        
        # URLs
        self.user_detail_url = reverse(
            'payments:transaction_detail',
            kwargs={'transaction_id': self.user_transaction.id}
        )
        self.other_user_detail_url = reverse(
            'payments:transaction_detail',
            kwargs={'transaction_id': self.other_user_transaction.id}
        )
    
    def test_transaction_detail_unauthenticated(self):
        """Test transaction detail requires authentication"""
        self.assert_login_required(self.user_detail_url, method='GET')
    
    def test_transaction_detail_own_transaction(self):
        """Test viewing detail of user's own transaction"""
        response = self.authenticated_client.get(self.user_detail_url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'transaction_detail.html')
        
        transaction = response.context['transaction']
        self.assertEqual(transaction.id, self.user_transaction.id)
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.amount, self.user_transaction.amount)
        self.assertEqual(transaction.transaction_type, 'funding')
        self.assertEqual(transaction.status, 'success')
    
    def test_transaction_detail_other_users_transaction(self):
        """Test viewing detail of another user's transaction returns 404"""
        response = self.authenticated_client.get(self.other_user_detail_url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_transaction_detail_nonexistent_transaction(self):
        """Test viewing detail of non-existent transaction returns 404"""
        nonexistent_id = uuid.uuid4()
        url = reverse(
            'payments:transaction_detail',
            kwargs={'transaction_id': nonexistent_id}
        )
        
        response = self.authenticated_client.get(url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_transaction_detail_invalid_uuid(self):
        """Test transaction detail with invalid UUID format"""
        invalid_url = reverse(
            'payments:transaction_detail',
            kwargs={'transaction_id': 'invalid-uuid'}
        ).replace('invalid-uuid', 'not-a-uuid')
        
        response = self.authenticated_client.get('/payments/transactions/not-a-uuid/')
        
        self.assertEqual(response.status_code, 404)
    
    def test_transaction_detail_contains_all_fields(self):
        """Test that transaction detail contains all necessary fields"""
        response = self.authenticated_client.get(self.user_detail_url)
        
        transaction = response.context['transaction']
        
        # Verify all important fields are accessible
        self.assertIsNotNone(transaction.id)
        self.assertIsNotNone(transaction.user)
        self.assertIsNotNone(transaction.gateway)
        self.assertIsNotNone(transaction.transaction_type)
        self.assertIsNotNone(transaction.amount)
        self.assertIsNotNone(transaction.currency)
        self.assertIsNotNone(transaction.gateway_reference)
        self.assertIsNotNone(transaction.internal_reference)
        self.assertIsNotNone(transaction.status)
        self.assertIsNotNone(transaction.created_at)
        self.assertIsNotNone(transaction.updated_at)
    
    def test_transaction_detail_with_paystack_details(self):
        """Test transaction detail includes Paystack-specific details"""
        response = self.authenticated_client.get(self.user_detail_url)
        
        transaction = response.context['transaction']
        
        # Verify Paystack details are accessible
        self.assertTrue(hasattr(transaction, 'paystack_details'))
        paystack_details = transaction.paystack_details
        
        self.assertEqual(paystack_details.paystack_reference, 'PS_DETAIL_REF')
        self.assertEqual(
            paystack_details.authorization_url,
            'https://checkout.paystack.com/detail_test'
        )
    
    def test_transaction_detail_withdrawal_transaction(self):
        """Test transaction detail for withdrawal transaction"""
        # Create a withdrawal transaction for the user
        withdrawal_transaction = self.create_payment_transaction(
            user=self.user,
            transaction_type='withdrawal',
            amount='200.00',
            status='pending',
            gateway_reference='USER_WITHDRAWAL_REF'
        )
        
        withdrawal_paystack = self.create_paystack_transaction(
            withdrawal_transaction,
            paystack_reference='PS_WITHDRAWAL_REF',
            recipient_code='RCP_test123',
            bank_code='044',
            account_number='1234567890',
            account_name='Test User'
        )
        
        withdrawal_url = reverse(
            'payments:transaction_detail',
            kwargs={'transaction_id': withdrawal_transaction.id}
        )
        
        response = self.authenticated_client.get(withdrawal_url)
        
        self.assertEqual(response.status_code, 200)
        
        transaction = response.context['transaction']
        self.assertEqual(transaction.transaction_type, 'withdrawal')
        self.assertEqual(transaction.amount, 200)
        
        # Verify withdrawal-specific Paystack details
        paystack_details = transaction.paystack_details
        self.assertEqual(paystack_details.recipient_code, 'RCP_test123')
        self.assertEqual(paystack_details.bank_code, '044')
        self.assertEqual(paystack_details.account_number, '1234567890')
        self.assertEqual(paystack_details.account_name, 'Test User')
    
    def test_transaction_detail_different_statuses(self):
        """Test transaction detail for transactions with different statuses"""
        statuses = ['pending', 'success', 'failed', 'cancelled']
        
        for status in statuses:
            with self.subTest(status=status):
                transaction = self.create_payment_transaction(
                    user=self.user,
                    transaction_type='funding',
                    amount='100.00',
                    status=status,
                    gateway_reference=f'STATUS_TEST_{status.upper()}'
                )
                
                url = reverse(
                    'payments:transaction_detail',
                    kwargs={'transaction_id': transaction.id}
                )
                
                response = self.authenticated_client.get(url)
                
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['transaction'].status, status) 