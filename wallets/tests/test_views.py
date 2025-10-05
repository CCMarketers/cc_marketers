# wallets/tests/test_views.py
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from decimal import Decimal
from unittest.mock import patch
import uuid

from ..models import Wallet, Transaction, WithdrawalRequest, EscrowTransaction
from ..forms import WithdrawalRequestForm, FundWalletForm
from ..services import WalletService
from .test_base import WalletTestCase, MockPaystackMixin
from subscriptions.models import UserSubscription

User = get_user_model()


class WalletDashboardViewTest(WalletTestCase):
    """Test WalletDashboardView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:dashboard')
    
    def test_login_required(self):
        """Test that login is required to access dashboard"""
        self.assert_requires_login(self.url)
    
    def test_dashboard_get_success(self):
        """Test successful dashboard GET request"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/dashboard.html')
        self.assert_context_contains(response, 'wallet')
        self.assertEqual(response.context['wallet'], self.wallet)
    
    def test_dashboard_context_data(self):
        """Test dashboard context data calculation"""
        # Create some transactions
        WalletService.credit_wallet(self.user, Decimal('100.00'), 'task_earning')
        WalletService.credit_wallet(self.user, Decimal('50.00'), 'referral_bonus')
        WalletService.credit_wallet(self.user, Decimal('25.00'), 'funding')  # Not counted in total_earned
        WalletService.debit_wallet(self.user, Decimal('30.00'), 'withdrawal')
        
        # Create pending withdrawal
        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('20.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account',
            bank_name='Test Bank',
            status='pending'
        )
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        # Check calculated context values
        self.assertEqual(response.context['total_earned'], Decimal('150.00'))  # task_earning + referral_bonus
        self.assertEqual(response.context['total_withdrawn'], Decimal('30.00'))
        self.assertEqual(response.context['pending_withdrawals'], Decimal('20.00'))
        self.assertEqual(response.context['wallet_balance'], Decimal('145.00'))  # 100 + 50 + 25 - 30
        self.assertEqual(response.context['available_balance'], Decimal('125.00'))  # wallet_balance - pending_withdrawals
    
    def test_recent_transactions_displayed(self):
        """Test that recent transactions are displayed"""
        # Create more than 10 transactions to test limit
        for i in range(15):
            WalletService.credit_wallet(
                self.user, 
                Decimal(f'{i + 1}.00'), 
                'funding',
                description=f'Transaction {i + 1}'
            )
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        # Should only show last 10 transactions
        recent_transactions = response.context['recent_transactions']
        self.assertEqual(len(recent_transactions), 10)
        
        # Should be ordered by most recent first
        self.assertEqual(recent_transactions[0].amount, Decimal('15.00'))
        self.assertEqual(recent_transactions[9].amount, Decimal('6.00'))
    
    def test_wallet_auto_creation(self):
        """Test that wallet is auto-created if doesn't exist"""
        new_user = User.objects.create_user(
            username='newuser',
            email='new@example.com',
            password='newpass123'
        )
        
        # Delete any auto-created wallet
        Wallet.objects.filter(user=new_user).delete()
        
        self.client.force_login(new_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Wallet.objects.filter(user=new_user).exists())


class TransactionListViewTest(WalletTestCase):
    """Test TransactionListView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:transactions')
        
        # Create subscription for user
        self.create_subscription(self.user, self.basic_plan)
        
        # Create test transactions
        WalletService.credit_wallet(self.user, Decimal('100.00'), 'task_earning')
        WalletService.credit_wallet(self.user, Decimal('50.00'), 'referral_bonus')
        WalletService.debit_wallet(self.user, Decimal('25.00'), 'withdrawal')
    
    def test_login_required(self):
        """Test that login is required"""
        self.assert_requires_login(self.url)
    
    def test_subscription_required(self):
        """Test that subscription is required"""
        # Remove subscription
        UserSubscription.objects.filter(user=self.user).delete()
        self.assert_requires_subscription(self.url)
    
    def test_transaction_list_get_success(self):
        """Test successful transaction list GET request"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/transactions.html')
        self.assert_context_contains(response, 'transactions')
        
        # Should show user's transactions only
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 3)
        for txn in transactions:
            self.assertEqual(txn.user, self.user)
    
    def test_transaction_list_filters_by_type(self):
        """Test filtering transactions by type"""
        self.client.force_login(self.user)
        
        # Filter by credit transactions
        response = self.client.get(self.url, {'type': 'credit'})
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 2)
        for txn in transactions:
            self.assertEqual(txn.transaction_type, 'credit')
        
        # Filter by debit transactions
        response = self.client.get(self.url, {'type': 'debit'})
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 1)
        self.assertEqual(transactions[0].transaction_type, 'debit')
    
    def test_transaction_list_filters_by_category(self):
        """Test filtering transactions by category"""
        self.client.force_login(self.user)
        
        # Filter by task_earning category
        response = self.client.get(self.url, {'category': 'task_earning'})
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 1)
        self.assertEqual(transactions[0].category, 'task_earning')
    
    def test_transaction_list_filters_by_status(self):
        """Test filtering transactions by status"""
        # Create pending transaction
        Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('75.00'),
            balance_before=Decimal('125.00'),
            balance_after=Decimal('200.00'),
            status='pending'
        )
        
        self.client.force_login(self.user)
        
        # Filter by success status
        response = self.client.get(self.url, {'status': 'success'})
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 3)  # Original 3 transactions
        
        # Filter by pending status
        response = self.client.get(self.url, {'status': 'pending'})
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 1)
        self.assertEqual(transactions[0].status, 'pending')
    
    def test_transaction_list_pagination(self):
        """Test transaction list pagination"""
        # Create more transactions than page limit (20)
        for i in range(25):
            WalletService.credit_wallet(
                self.user, 
                Decimal(f'{i + 1}.00'), 
                'funding'
            )
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        # Should be paginated
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['transactions']), 20)
        
        # Test second page
        response = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(response.context['transactions']), 8)  # 3 original + 25 new = 28 total, 8 on page 2
    
    def test_transaction_list_context(self):
        """Test context variables provided to template"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        self.assert_context_contains(response, 'transaction_types')
        self.assert_context_contains(response, 'transaction_categories')
        self.assert_context_contains(response, 'transaction_status')
        
        # Verify context values match model choices
        self.assertEqual(response.context['transaction_types'], Transaction.TRANSACTION_TYPES)
        self.assertEqual(response.context['transaction_categories'], Transaction.TRANSACTION_CATEGORIES)
        self.assertEqual(response.context['transaction_status'], Transaction.TRANSACTION_STATUS)
    
    def test_other_user_transactions_not_visible(self):
        """Test that other users' transactions are not visible"""
        # Create transaction for other user
        WalletService.credit_wallet(self.other_user, Decimal('999.00'), 'funding')
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        # Should only see own transactions
        transactions = response.context['transactions']
        for txn in transactions:
            self.assertEqual(txn.user, self.user)
            self.assertNotEqual(txn.amount, Decimal('999.00'))


class WithdrawalRequestViewTest(WalletTestCase):
    """Test WithdrawalRequestView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:withdrawal_request')
        
        # Create business subscription for user
        self.create_subscription(self.user, self.business_plan)
        
        # Fund user wallet
        WalletService.credit_wallet(self.user, Decimal('500.00'), 'funding')
        
        self.valid_data = {
            'amount': Decimal('100.00'),
            'withdrawal_method': 'paystack',
            'account_number': '1234567890',
            'account_name': 'Test Account',
            'bank_name': 'Test Bank',
            'bank_code': '001'
        }
    
    def test_login_required(self):
        """Test that login is required"""
        self.assert_requires_login(self.url, 'post', self.valid_data)
    
    def test_subscription_required(self):
        """Test that subscription is required"""
        UserSubscription.objects.filter(user=self.user).delete()
        self.assert_requires_subscription(self.url)
    
    def test_business_plan_required(self):
        """Test that business plan is required"""
        # Change to basic plan
        subscription = UserSubscription.objects.get(user=self.user)
        subscription.plan = self.basic_plan
        subscription.save()
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)  # Redirected due to plan requirement
    
    def test_withdrawal_request_get_success(self):
        """Test successful GET request to withdrawal form"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/withdrawal_request.html')
        self.assertIsInstance(response.context['form'], WithdrawalRequestForm)
        self.assert_context_contains(response, 'wallet')
        self.assert_context_contains(response, 'available_balance')
    
    def test_withdrawal_request_post_success(self):
        """Test successful withdrawal request submission"""
        self.client.force_login(self.user)
        response = self.client.post(self.url, self.valid_data)
        
        # Should redirect to withdrawal list
        self.assertRedirects(response, reverse('wallets:withdrawal_list'))
        
        # Should create withdrawal request
        withdrawal = WithdrawalRequest.objects.get(user=self.user)
        self.assertEqual(withdrawal.amount, self.valid_data['amount'])
        self.assertEqual(withdrawal.withdrawal_method, self.valid_data['withdrawal_method'])
        self.assertEqual(withdrawal.account_number, self.valid_data['account_number'])
        self.assertEqual(withdrawal.status, 'pending')
        
        # Should show success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('successfully' in str(msg) for msg in messages))
    
    def test_withdrawal_request_insufficient_funds(self):
        """Test withdrawal request with insufficient funds"""
        # Try to withdraw more than available
        invalid_data = self.valid_data.copy()
        invalid_data['amount'] = Decimal('600.00')  # User only has 500
        
        self.client.force_login(self.user)
        response = self.client.post(self.url, invalid_data)
        
        # Should stay on form with error
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/withdrawal_request.html')
        
        # Should show error message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Insufficient balance' in str(msg) for msg in messages))
        
        # Should not create withdrawal request
        self.assertFalse(WithdrawalRequest.objects.filter(user=self.user).exists())
    
    def test_withdrawal_request_form_validation_error(self):
        """Test withdrawal request with form validation errors"""
        invalid_data = self.valid_data.copy()
        invalid_data['amount'] = Decimal('0.50')  # Below minimum

        self.client.force_login(self.user)
        response = self.client.post(self.url, invalid_data)

        self.assertEqual(response.status_code, 200)
        # Check form errors directly in context
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertIn('amount', form.errors)
        self.assertEqual(form.errors['amount'][0], 'Minimum withdrawal amount is $1.00')


    def test_available_balance_calculation_with_pending_withdrawals(self):
        """Test available balance calculation considers pending withdrawals"""
        # Create pending withdrawal
        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account',
            bank_name='Test Bank',
            status='pending'
        )
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        # Available balance should be 500 - 100 = 400
        self.assertEqual(response.context['available_balance'], Decimal('400.00'))


class WithdrawalListViewTest(WalletTestCase):
    """Test WithdrawalListView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:withdrawal_list')
        
        # Create business subscription
        self.create_subscription(self.user, self.business_plan)
        
        # Create withdrawal requests
        self.withdrawal1 = WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account 1',
            bank_name='Test Bank 1',
            status='pending'
        )
        
        self.withdrawal2 = WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('200.00'),
            withdrawal_method='bank_transfer',
            account_number='0987654321',
            account_name='Test Account 2',
            bank_name='Test Bank 2',
            status='completed'
        )
    
    def test_login_required(self):
        """Test that login is required"""
        self.assert_requires_login(self.url)
    
    def test_subscription_required(self):
        """Test that subscription is required"""
        UserSubscription.objects.filter(user=self.user).delete()
        self.assert_requires_subscription(self.url)
    
    def test_business_plan_required(self):
        """Test that business plan is required"""
        # Change to basic plan
        subscription = UserSubscription.objects.get(user=self.user)
        subscription.plan = self.basic_plan
        subscription.save()
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
    
    def test_withdrawal_list_success(self):
        """Test successful withdrawal list view"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/withdrawal_list.html')
        
        withdrawals = response.context['withdrawals']
        self.assertEqual(withdrawals.count(), 2)
        self.assertIn(self.withdrawal1, withdrawals)
        self.assertIn(self.withdrawal2, withdrawals)
    
    def test_withdrawal_list_only_user_withdrawals(self):
        """Test that only user's withdrawals are shown"""
        # Create withdrawal for other user
        WithdrawalRequest.objects.create(
            user=self.other_user,
            amount=Decimal('999.00'),
            withdrawal_method='paystack',
            account_number='9999999999',
            account_name='Other Account',
            bank_name='Other Bank',
            status='pending'
        )
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        withdrawals = response.context['withdrawals']
        self.assertEqual(withdrawals.count(), 2)  # Only user's withdrawals
        for withdrawal in withdrawals:
            self.assertEqual(withdrawal.user, self.user)
    
    def test_withdrawal_list_pagination(self):
        """Test withdrawal list pagination"""
        # Create many withdrawals
        for i in range(15):
            WithdrawalRequest.objects.create(
                user=self.user,
                amount=Decimal(f'{i + 10}.00'),
                withdrawal_method='paystack',
                account_number=f'123456789{i}',
                account_name=f'Test Account {i}',
                bank_name='Test Bank',
                status='pending'
            )
        
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        # Should be paginated (10 per page)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['withdrawals']), 10)


class FundWalletViewTest(WalletTestCase):
    """Test FundWalletView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:fund_wallet')
    
    def test_login_required(self):
        """Test that login is required"""
        self.assert_requires_login(self.url)
    
    def test_fund_wallet_get_success(self):
        """Test successful GET request to fund wallet form"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/fund_wallet.html')
        self.assertIsInstance(response.context['form'], FundWalletForm)
    
    def test_fund_wallet_form_display(self):
        """Test that fund wallet form is properly displayed"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        form = response.context['form']
        self.assertIn('amount', form.fields)
        self.assertIn('description', form.fields)


class AdminWithdrawalListViewTest(WalletTestCase):
    """Test AdminWithdrawalListView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:admin_withdrawal_list')
        
        # Create withdrawal requests from different users
        self.withdrawal1 = WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='User Account',
            bank_name='User Bank',
            status='pending'
        )
        
        self.withdrawal2 = WithdrawalRequest.objects.create(
            user=self.other_user,
            amount=Decimal('200.00'),
            withdrawal_method='bank_transfer',
            account_number='0987654321',
            account_name='Other Account',
            bank_name='Other Bank',
            status='completed'
        )
    
    def test_staff_required(self):
        """Test that staff access is required"""
        self.assert_requires_staff(self.url)
    
    def test_admin_withdrawal_list_success(self):
        """Test successful admin withdrawal list view"""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/admin/withdrawal_list.html')
        
        # Should show all withdrawals
        withdrawals = response.context['withdrawals']
        self.assertEqual(withdrawals.count(), 2)
        self.assertIn(self.withdrawal1, withdrawals)
        self.assertIn(self.withdrawal2, withdrawals)
    
    def test_admin_withdrawal_list_filter_by_status(self):
        """Test filtering withdrawals by status"""
        self.client.force_login(self.admin_user)
        
        # Filter by pending status
        response = self.client.get(self.url, {'status': 'pending'})
        withdrawals = response.context['withdrawals']
        self.assertEqual(withdrawals.count(), 1)
        self.assertEqual(withdrawals[0], self.withdrawal1)
        
        # Filter by completed status
        response = self.client.get(self.url, {'status': 'completed'})
        withdrawals = response.context['withdrawals']
        self.assertEqual(withdrawals.count(), 1)
        self.assertEqual(withdrawals[0], self.withdrawal2)


class AdminWithdrawalDetailViewTest(WalletTestCase, MockPaystackMixin):
    """Test AdminWithdrawalDetailView functionality"""
    
    def setUp(self):
        super().setUp()
        
        # Fund user wallet for withdrawal processing
        WalletService.credit_wallet(self.user, Decimal('500.00'), 'funding')
        
        self.withdrawal = WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account',
            bank_name='Test Bank',
            bank_code='001',
            status='pending'
        )
        
        self.url = reverse('wallets:admin_withdrawal_detail', kwargs={'pk': self.withdrawal.pk})
    
    def test_staff_required(self):
        """Test that staff access is required"""
        self.assert_requires_staff(self.url)
    
    def test_admin_withdrawal_detail_get_success(self):
        """Test successful GET request to withdrawal detail"""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/admin/withdrawal_detail.html')
        self.assertEqual(response.context['withdrawal'], self.withdrawal)
    
    @patch('wallets.services.WalletService.approve_withdrawal')
    def test_admin_approve_withdrawal_success(self, mock_approve):
        """Test successful withdrawal approval"""
        mock_approve.return_value = None  # Mock successful approval

        Wallet.objects.get(user=self.user).balance

        self.client.force_login(self.admin_user)
        response = self.client.post(self.url, {'action': 'approve'})

        # Check service was called
        mock_approve.assert_called_once_with(self.withdrawal.id, self.admin_user)
        
        # Should redirect back to detail page
        self.assertRedirects(response, self.url)
        
        # Should show success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('approved successfully' in str(msg) for msg in messages))


    @patch('wallets.services.WalletService.approve_withdrawal')
    def test_admin_approve_withdrawal_paystack_failure(self, mock_approve):
        """Test withdrawal approval with Paystack failure"""
        # Mock service to raise an error
        mock_approve.side_effect = ValueError("Paystack transfer failed")

        self.client.force_login(self.admin_user)
        response = self.client.post(self.url, {'action': 'approve'}, follow=True)  # Add follow=True

        # Should show error message
        messages = list(get_messages(response.wsgi_request))
        # error_found = any('error' in str(msg).lower() for msg in messages)
        self.assertIn("Paystack transfer failed", [str(msg) for msg in messages])
        # self.assertTrue(error_found)


    def test_admin_reject_withdrawal_success(self):
        """Test successful withdrawal rejection"""
        rejection_reason = 'Suspicious account details'
        
        self.client.force_login(self.admin_user)
        response = self.client.post(self.url, {
            'action': 'reject',
            'reason': rejection_reason
        })
        
        # Should redirect back to detail page
        self.assertRedirects(response, self.url)
        
        # Check withdrawal was rejected
        self.withdrawal.refresh_from_db()
        self.assertEqual(self.withdrawal.status, 'rejected')
        self.assertEqual(self.withdrawal.processed_by, self.admin_user)
        self.assertEqual(self.withdrawal.admin_notes, rejection_reason)
        
        # Wallet should not be debited
        self.assert_wallet_balance(self.user, Decimal('500.00'))
        
        # Should show success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('rejected' in str(msg) for msg in messages))
    


    @patch('wallets.services.WalletService.approve_withdrawal')
    def test_admin_process_non_pending_withdrawal(self, mock_approve):
        """Test processing already processed withdrawal"""
        self.withdrawal.status = 'completed'
        self.withdrawal.save()
        
        # Mock service to raise an error for non-pending withdrawal
        mock_approve.side_effect = ValueError("Withdrawal is not pending")

        self.client.force_login(self.admin_user)
        response = self.client.post(self.url, {'action': 'approve'}, follow=True)  # Add follow=True
        
        # Should show error message
        messages = list(get_messages(response.wsgi_request))
        self.assertIn("Withdrawal is not pending", [str(msg) for msg in messages])



class WalletTransactionDetailViewTest(WalletTestCase):
    """Test wallet_transaction_detail view function"""
    
    def setUp(self):
        super().setUp()
        
        self.transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('100.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('100.00'),
            description='Test transaction'
        )
        
        self.url = reverse('wallets:transaction_detail', kwargs={'transaction_id': self.transaction.id})
    
    def test_login_required(self):
        """Test that login is required"""
        self.assert_requires_login(self.url)
    
    def test_transaction_detail_success(self):
        """Test successful transaction detail view"""
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/transaction_detail.html')
        self.assertEqual(response.context['transaction'], self.transaction)
    
    def test_transaction_detail_other_user_transaction(self):
        """Test accessing other user's transaction returns 404"""
        other_transaction = Transaction.objects.create(
            user=self.other_user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('200.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('200.00')
        )
        
        url = reverse('wallets:transaction_detail', kwargs={'transaction_id': other_transaction.id})
        
        self.client.force_login(self.user)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)
    
    def test_transaction_detail_nonexistent_transaction(self):
        """Test accessing nonexistent transaction returns 404"""
        nonexistent_id = uuid.uuid4()
        url = reverse('wallets:transaction_detail', kwargs={'transaction_id': nonexistent_id})
        
        self.client.force_login(self.user)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)


class AdminEscrowListViewTest(WalletTestCase):
    """Test AdminEscrowListView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:admin_escrow_list')
        
        # Create test tasks and escrows
        self.task1 = self.create_task(self.user, "Task 1", Decimal('100.00'))
        self.task2 = self.create_task(self.other_user, "Task 2", Decimal('200.00'))
        
        self.escrow1 = EscrowTransaction.objects.create(
            task=self.task1,
            advertiser=self.user,
            amount=Decimal('100.00'),
            status='locked'
        )
        
        self.escrow2 = EscrowTransaction.objects.create(
            task=self.task2,
            advertiser=self.other_user,
            amount=Decimal('200.00'),
            status='released'
        )
    
    def test_staff_required(self):
        """Test that staff access is required"""
        self.assert_requires_staff(self.url)
    
    def test_admin_escrow_list_success(self):
        """Test successful admin escrow list view"""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/admin/escrow_list.html')
        
        escrows = response.context['escrows']
        self.assertEqual(escrows.count(), 2)
        self.assertIn(self.escrow1, escrows)
        self.assertIn(self.escrow2, escrows)
    
    def test_admin_escrow_list_filter_by_status(self):
        """Test filtering escrows by status"""
        self.client.force_login(self.admin_user)
        
        # Filter by locked status
        response = self.client.get(self.url, {'status': 'locked'})
        escrows = response.context['escrows']
        self.assertEqual(escrows.count(), 1)
        self.assertEqual(escrows[0], self.escrow1)
        
        # Filter by released status
        response = self.client.get(self.url, {'status': 'released'})
        escrows = response.context['escrows']
        self.assertEqual(escrows.count(), 1)
        self.assertEqual(escrows[0], self.escrow2)


class AdminTransactionListViewTest(WalletTestCase):
    """Test AdminTransactionListView functionality"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('wallets:admin_transaction_list')
        
        # Create transactions for different users
        self.txn1 = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('100.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('100.00'),
            description='User funding'
        )
        
        self.txn2 = Transaction.objects.create(
            user=self.other_user,
            transaction_type='debit',
            category='withdrawal',
            amount=Decimal('50.00'),
            balance_before=Decimal('100.00'),
            balance_after=Decimal('50.00'),
            description='Other user withdrawal'
        )
    
    def test_staff_required(self):
        """Test that staff access is required"""
        self.assert_requires_staff(self.url)
    
    def test_admin_transaction_list_success(self):
        """Test successful admin transaction list view"""
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assert_template_used(response, 'wallets/admin/transaction_list.html')
        
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 2)
        self.assertIn(self.txn1, transactions)
        self.assertIn(self.txn2, transactions)
    
    def test_admin_transaction_list_search(self):
        """Test searching transactions"""
        self.client.force_login(self.admin_user)
        
        # Search by username
        response = self.client.get(self.url, {'search': self.user.username})
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 1)
        self.assertEqual(transactions[0], self.txn1)
        
        # Search by description
        response = self.client.get(self.url, {'search': 'funding'})
        transactions = response.context['transactions']
        self.assertEqual(transactions.count(), 1)
        self.assertEqual(transactions[0], self.txn1)
    
    def test_admin_transaction_list_pagination(self):
        """Test transaction list pagination"""
        # Create many transactions
        for i in range(60):
            Transaction.objects.create(
                user=self.user,
                transaction_type='credit',
                category='funding',
                amount=Decimal(f'{i + 1}.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal(f'{i + 1}.00')
            )
        
        self.client.force_login(self.admin_user)
        response = self.client.get(self.url)
        
        # Should be paginated (50 per page)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['transactions']), 50)