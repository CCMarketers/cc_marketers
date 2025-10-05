# tests/test_views_wallet.py
"""
Test suite for task wallet views including dashboard, transactions, and top-up functionality.
"""
from decimal import Decimal
from django.urls import reverse

from tasks.models import TaskWallet, TaskWalletTransaction
from wallets.models import  WithdrawalRequest
from tasks.services import TaskWalletService

from tasks.models import Task
from wallets.models import  EscrowTransaction

from .test_base import ComprehensiveTaskTestCase

from django.utils import timezone
from datetime import timedelta



class TaskWalletDashboardViewTest(ComprehensiveTaskTestCase):
    """Test cases for TaskWalletDashboardView."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:task_wallet_dashboard')

    def test_requires_login(self):
        """Test that task wallet dashboard requires login."""
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/login/?next={self.url}')

    def test_creates_wallet_if_not_exists(self):
        """Test that wallet is created if it doesn't exist."""
        # Delete existing wallet
        TaskWallet.objects.filter(user=self.advertiser).delete()
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/task_wallet_dashboard.html')
        
        # Check wallet was created
        wallet = TaskWallet.objects.get(user=self.advertiser)
        self.assertEqual(wallet.balance, Decimal('0.00'))

    def test_displays_existing_wallet(self):
        """Test that existing wallet is displayed."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['task_wallet'], self.advertiser_task_wallet)

    from django.utils import timezone
    from datetime import timedelta

    def test_shows_recent_transactions(self):
        """Test that recent transactions are shown."""
        now = timezone.now()
        for i in range(15):
            TaskWalletTransaction.objects.create(
                user=self.advertiser,
                transaction_type='credit',
                category='topup_from_main',
                amount=Decimal('10.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('10.00'),
                description=f'Transaction {i}',
                created_at=now + timedelta(seconds=i)  # ✅ unique timestamps
            )
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)

        transactions = response.context['transactions']
        self.assertEqual(len(transactions), 10)

        transaction_descriptions = [t.description for t in transactions]
        self.assertEqual(transaction_descriptions[0], 'Transaction 14')


    def test_wallet_balance_display(self):
        """Test that wallet balance is displayed correctly."""
        # Set specific balance
        self.advertiser_task_wallet.balance = Decimal('123.45')
        self.advertiser_task_wallet.save()
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        wallet = response.context['task_wallet']
        self.assertEqual(wallet.balance, Decimal('123.45'))

    def test_member_can_access_dashboard(self):
        """Test that members can also access the dashboard."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        # Should create wallet for member
        member_wallet = TaskWallet.objects.get(user=self.member)
        self.assertEqual(response.context['task_wallet'], member_wallet)


class TaskWalletTransactionListViewTest(ComprehensiveTaskTestCase):
    """Test cases for TaskWalletTransactionListView."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:task_wallet_transactions')

    def test_requires_login(self):
        """Test that transaction list requires login."""
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/login/?next={self.url}')

    def test_shows_only_user_transactions(self):
        """Test that only current user's transactions are shown."""
        # Create transactions for advertiser
        advertiser_txn = TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='credit',
            category='topup_from_main',
            amount=Decimal('50.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50.00')
        )
        
        # Create transactions for another user
        another_user = self.create_user('another', 'another@test.com')
        other_txn = TaskWalletTransaction.objects.create(
            user=another_user,
            transaction_type='credit',
            category='topup_from_main',
            amount=Decimal('25.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('25.00')
        )
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/transactions.html')
        
        transactions = response.context['transactions']
        transaction_ids = [str(t.id) for t in transactions]
        
        self.assertIn(str(advertiser_txn.id), transaction_ids)
        self.assertNotIn(str(other_txn.id), transaction_ids)

    def test_pagination_works(self):
        """Test that pagination works correctly."""
        # Create 25 transactions (more than 20 per page limit)
        for i in range(25):
            TaskWalletTransaction.objects.create(
                user=self.advertiser,
                transaction_type='credit',
                category='topup_from_main',
                amount=Decimal('10.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('10.00')
            )
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        transactions = response.context['transactions']
        self.assertEqual(len(transactions), 20)  # First page should have 20
        
        # Test second page
        response = self.client.get(self.url, {'page': 2})
        transactions = response.context['transactions']
        self.assertEqual(len(transactions), 5)  # Second page should have remaining 5

    def test_transactions_ordered_newest_first(self):
        """Test that transactions are ordered by creation date (newest first)."""
        # Create transactions with specific order
        txn1 = TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='credit',
            category='topup_from_main',
            amount=Decimal('10.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('10.00'),
            description='First transaction'
        )
        
        txn2 = TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='debit',
            category='task_posting',
            amount=Decimal('5.00'),
            balance_before=Decimal('10.00'),
            balance_after=Decimal('5.00'),
            description='Second transaction'
        )
        self.advertiser_task_wallet.refresh_from_db()

        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        self.advertiser_task_wallet.refresh_from_db()

        transactions = list(response.context['transactions'])
        # Most recent should come first
        self.advertiser_task_wallet.refresh_from_db()

        self.assertEqual(transactions[0], txn2)
        self.advertiser_task_wallet.refresh_from_db()

        self.assertEqual(transactions[1], txn1)

    def test_empty_transaction_list(self):
        """Test display when user has no transactions."""
        # Delete all transactions for user
        TaskWalletTransaction.objects.filter(user=self.advertiser).delete()
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        transactions = response.context['transactions']
        self.assertEqual(len(transactions), 0)


class TaskWalletTopupViewTest(ComprehensiveTaskTestCase):
    """Test cases for TaskWalletTopupView."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:task_wallet_topup')
        
        # Ensure advertiser has sufficient main wallet balance
        self.advertiser_wallet.balance = Decimal('200.00')
        self.advertiser_wallet.save()

    def test_requires_login(self):
        """Test that topup requires login."""
        response = self.client.get(self.url)
        self.assertRedirects(response, f'/login/?next={self.url}')

    def test_get_topup_form(self):
        """Test GET request shows topup form."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/topup.html')
        self.assertIsNotNone(response.context['form'])

    def test_shows_available_balance(self):
        """Test that available balance is shown in context."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        # Should show main wallet balance minus pending withdrawals
        self.assertEqual(response.context['available_balance'], Decimal('200.00'))

    def test_available_balance_excludes_pending_withdrawals(self):
        """Test that pending withdrawals are excluded from available balance."""
        # Create pending withdrawal
        WithdrawalRequest.objects.create(
            user=self.advertiser,
            amount=Decimal('50.00'),
            status='pending'
        )
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        # Available balance should be reduced by pending withdrawal
        expected_balance = Decimal('200.00') - Decimal('50.00')
        self.assertEqual(response.context['available_balance'], expected_balance)

    def test_successful_topup(self):
        """Test successful task wallet topup."""
        initial_main_balance = self.advertiser_wallet.balance
        initial_task_balance = self.advertiser_task_wallet.balance
        topup_amount = Decimal('75.00')
        
        self.login_user(self.advertiser)
        
        data = {'amount': str(topup_amount)}
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:task_wallet_dashboard'))
        
        # Check balances were updated
        self.advertiser_wallet.refresh_from_db()
        self.advertiser_task_wallet.refresh_from_db()
        
        self.assertEqual(self.advertiser_wallet.balance, initial_main_balance - topup_amount)
        self.assertEqual(self.advertiser_task_wallet.balance, initial_task_balance + topup_amount)
        
        # Check success message
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any(f'Task Wallet topped up with ${topup_amount}' in str(m) for m in messages_list))

    def test_topup_creates_transactions(self):
        """Test that topup creates appropriate transactions."""
        topup_amount = Decimal('100.00')
        
        self.login_user(self.advertiser)
        
        data = {'amount': str(topup_amount)}
        self.client.post(self.url, data)
        
        # Check main wallet debit transaction exists
        from wallets.models import Transaction
        main_txn = Transaction.objects.filter(
            user=self.advertiser,
            transaction_type='debit',
            amount=topup_amount,
            category='task_wallet_topup'
        ).first()
        self.assertIsNotNone(main_txn)
        
        # Check task wallet credit transaction exists
        task_txn = TaskWalletTransaction.objects.filter(
            user=self.advertiser,
            transaction_type='credit',
            amount=topup_amount,
            category='topup_from_main'
        ).first()
        self.assertIsNotNone(task_txn)
        
        # Check transactions are linked by reference
        self.assertEqual(task_txn.reference, main_txn.reference)

    def test_insufficient_balance_handling(self):
        """Test handling of insufficient main wallet balance."""
        # Set main wallet balance lower than topup amount
        self.advertiser_wallet.balance = Decimal('25.00')
        self.advertiser_wallet.save()
        
        topup_amount = Decimal('50.00')  # More than available
        
        self.login_user(self.advertiser)
        
        data = {'amount': str(topup_amount)}
        response = self.client.post(self.url, data)
        
        # Should show form with error
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/topup.html')
        
        # Check error message
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('Insufficient' in str(m) for m in messages_list))
        
        # Balances should remain unchanged
        self.advertiser_wallet.refresh_from_db()
        self.advertiser_task_wallet.refresh_from_db()
        self.assertEqual(self.advertiser_wallet.balance, Decimal('25.00'))

    def test_form_validation_minimum_amount(self):
        """Test form validation for minimum topup amount."""
        self.login_user(self.advertiser)
        
        data = {'amount': '0.50'}  # Below minimum of 1.00
        response = self.client.post(self.url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertIn('amount', form.errors)

    def test_form_validation_invalid_amount(self):
        """Test form validation for invalid amount."""
        self.login_user(self.advertiser)
        
        data = {'amount': 'invalid'}
        response = self.client.post(self.url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertIn('amount', form.errors)

    def test_form_validation_negative_amount(self):
        """Test form validation for negative amount."""
        self.login_user(self.advertiser)
        
        data = {'amount': '-10.00'}
        response = self.client.post(self.url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)

    def test_topup_with_exact_available_balance(self):
        """Test topup with exact available balance."""
        available_balance = Decimal('200.00')
        
        self.login_user(self.advertiser)
        
        data = {'amount': str(available_balance)}
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:task_wallet_dashboard'))
        
        # Main wallet should be zero
        self.advertiser_wallet.refresh_from_db()
        self.assertEqual(self.advertiser_wallet.balance, Decimal('0.00'))

    def test_topup_rounds_to_two_decimals(self):
        """Test that topup amounts are properly rounded to two decimal places."""
        self.login_user(self.advertiser)
        
        data = {'amount': '25.123'}  # More than 2 decimal places
        response = self.client.post(self.url, data)
        
        if response.status_code == 302:  # Successful redirect
            # Check that amount was rounded
            task_txn = TaskWalletTransaction.objects.filter(
                user=self.advertiser,
                transaction_type='credit',
                category='topup_from_main'
            ).first()
            # Amount should be rounded to 25.12
            self.assertEqual(task_txn.amount, Decimal('25.12'))

    def test_concurrent_topup_handling(self):
        """Test handling of concurrent topup attempts."""
        # This is a simplified test - full concurrency testing would require threading
        self.login_user(self.advertiser)
        
        # Make multiple quick requests
        data = {'amount': '50.00'}
        response1 = self.client.post(self.url, data)
        response2 = self.client.post(self.url, data)
        
        # At least one should succeed
        success_count = sum(1 for r in [response1, response2] if r.status_code == 302)
        self.assertGreaterEqual(success_count, 1)
        
        # Total deducted from main wallet should not exceed available balance
        self.advertiser_wallet.refresh_from_db()
        self.assertGreaterEqual(self.advertiser_wallet.balance, Decimal('0.00'))


class TaskWalletIntegrationTest(ComprehensiveTaskTestCase):
    """Integration tests for task wallet functionality."""
    
    def test_complete_task_wallet_workflow(self):
        """Test complete workflow: topup -> create task -> escrow -> release."""
        # 1. Start with empty task wallet
        self.advertiser_task_wallet.balance = Decimal('0.00')
        self.advertiser_task_wallet.save()
        
        # 2. Top up task wallet
        self.login_user(self.advertiser)
        topup_url = reverse('tasks:task_wallet_topup')
        topup_data = {'amount': '100.00'}
        response = self.client.post(topup_url, topup_data)
        
        self.assertRedirects(response, reverse('tasks:task_wallet_dashboard'))
        
        # 3. Create task (this should create escrow)
        create_url = reverse('tasks:create_task')
        task_data = {
            'title': 'Integration Test Task',
            'description': 'Test task for integration',
            'payout_per_slot': '20.00',
            'total_slots': '2',
            'deadline': (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Provide proof'
        }
        response = self.client.post(create_url, task_data)
        
        # Task should be created and escrow locked
        task = Task.objects.get(title='Integration Test Task')
        escrow = EscrowTransaction.objects.get(task=task)
        self.assertEqual(escrow.amount, Decimal('40.00'))  # 20.00 * 2
        
        # 4. Submit to task
        submission = self.create_submission(task=task, member=self.member)
        
        # 5. Approve submission (should release escrow)
        review_url = reverse('tasks:review_submission', kwargs={'submission_id': submission.id})
        review_data = {'decision': 'approve'}
        response = self.client.post(review_url, review_data)
        
        # Check that escrow was released and balances updated
        escrow.refresh_from_db()
        self.assertEqual(escrow.status, 'released')

            
    def test_task_wallet_balance_consistency(self):
        """Test that task wallet balance remains consistent across operations."""
        self.advertiser_task_wallet.refresh_from_db()  # ✅ refresh first
        initial_balance = self.advertiser_task_wallet.balance
        
        TaskWalletService.credit_wallet(
            user=self.advertiser,
            amount=Decimal('50.00'),
            category='admin_adjustment'
        )
        
        TaskWalletService.debit_wallet(
            user=self.advertiser,
            amount=Decimal('30.00'),
            category='task_posting'
        )
        
        self.advertiser_task_wallet.refresh_from_db()
        expected_balance = initial_balance + Decimal('50.00') - Decimal('30.00')
        self.assertEqual(self.advertiser_task_wallet.balance, expected_balance)
        
        # Recompute from transactions
        transactions = TaskWalletTransaction.objects.filter(user=self.advertiser)
        # Use the actual initial balance in recomputation
        transactions = TaskWalletTransaction.objects.filter(user=self.advertiser)
        credit_total = sum(t.amount for t in transactions if t.transaction_type == 'credit')
        debit_total = sum(t.amount for t in transactions if t.transaction_type == 'debit')

        calculated_balance = initial_balance + credit_total - debit_total
        self.assertEqual(self.advertiser_task_wallet.balance, calculated_balance)





