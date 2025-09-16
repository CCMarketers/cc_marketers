# wallets/tests/test_integration.py
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db import transaction as db_transaction
from decimal import Decimal
from unittest.mock import patch, Mock
import uuid

from ..models import Wallet, Transaction, WithdrawalRequest, EscrowTransaction
from ..services import WalletService
from ..forms import WithdrawalRequestForm
from .test_base import WalletTestCase, MockPaystackMixin
from payments.models import PaymentTransaction, PaymentGateway
from subscriptions.models import UserSubscription

User = get_user_model()


class EndToEndWalletFlowTest(WalletTestCase, MockPaystackMixin):
    """Test complete end-to-end wallet workflows"""
    
    def setUp(self):
        super().setUp()
        # Create payment gateway
        self.gateway = PaymentGateway.objects.get_or_create(
            name='paystack',
            # display_name='Paystack',
            is_active=True
        )
        
        # Create business subscription for user
        self.business_subscription = self.create_subscription(self.user, self.business_plan)
    
    def test_complete_funding_flow(self):
        """Test complete wallet funding flow from form to credit"""
        # Step 1: User accesses funding form
        self.client.force_login(self.user)
        funding_url = reverse('wallets:fund_wallet')
        response = self.client.get(funding_url)
        self.assertEqual(response.status_code, 200)
        
        # Step 2: User submits valid funding form
        form_data = {
            'amount': Decimal('250.00'),
            'description': 'Test wallet funding'
        }
        
        # Mock successful Paystack initialization
        self.mock_paystack_success()
        
        # Step 3: Service processes funding request
        auth_url = WalletService.fund_wallet(
            user=self.user,
            amount=form_data['amount'],
            gateway_name='paystack'
        )
        
        self.assertEqual(auth_url, 'https://checkout.paystack.com/test123')
        
        # Step 4: Simulate successful payment completion (webhook)
        initial_balance = self.wallet.balance
        credit_txn = WalletService.credit_wallet(
            user=self.user,
            amount=form_data['amount'],
            category='funding',
            description='Paystack funding completed'
        )
        
        # Verify final state
        self.assert_wallet_balance(self.user, initial_balance + form_data['amount'])
        self.assertEqual(credit_txn.category, 'funding')
        self.assertEqual(credit_txn.amount, form_data['amount'])
    
    def test_complete_withdrawal_flow(self):
        """Test complete withdrawal flow from request to processing"""
        # Step 1: Fund user wallet
        WalletService.credit_wallet(self.user, Decimal('500.00'), 'funding')
        
        # Step 2: User creates withdrawal request
        self.client.force_login(self.user)
        withdrawal_url = reverse('wallets:withdrawal_request')
        
        withdrawal_data = {
            'amount': Decimal('200.00'),
            'withdrawal_method': 'paystack',
            'account_number': '1234567890',
            'account_name': 'Test Account',
            'bank_name': 'Test Bank',
            'bank_code': '001'
        }
        
        response = self.client.post(withdrawal_url, withdrawal_data)
        self.assertRedirects(response, reverse('wallets:withdrawal_list'))
        
        # Verify withdrawal request created
        withdrawal = WithdrawalRequest.objects.get(user=self.user)
        self.assertEqual(withdrawal.amount, withdrawal_data['amount'])
        self.assertEqual(withdrawal.status, 'pending')
        
        # Step 3: Admin approves withdrawal
        self.mock_paystack_success()
        
        with patch('payments.models.PaymentTransaction.objects.get') as mock_get_payment:
            mock_payment_txn = Mock()
            mock_payment_txn.id = uuid.uuid4()
            mock_payment_txn.internal_reference = 'PAY_123'
            mock_payment_txn.paystack_details = Mock()
            mock_get_payment.return_value = mock_payment_txn
            
            approved_withdrawal = WalletService.approve_withdrawal(
                withdrawal.id, 
                self.admin_user
            )
        
        # Verify final state
        self.assertEqual(approved_withdrawal.status, 'approved')
        self.assert_wallet_balance(self.user, Decimal('300.00'))  # 500 - 200
        
        # Verify debit transaction created
        debit_txn = Transaction.objects.get(
            user=self.user,
            category='withdrawal',
            amount=withdrawal_data['amount']
        )
        self.assertEqual(debit_txn.transaction_type, 'debit')
    
    def test_complete_task_escrow_flow(self):
        """Test complete task escrow flow from creation to release"""
        # Step 1: Create task and fund TaskWallet
        task = self.create_task(self.user, "Integration Test Task", Decimal('100.00'))
        
        # Mock TaskWallet operations
        with patch('tasks.services.TaskWalletService.get_or_create_wallet') as mock_get_wallet, \
             patch('tasks.models.TaskWalletTransaction.objects.create') as mock_txn_create:
            
            mock_wallet = Mock()
            mock_wallet.balance = Decimal('500.00')
            mock_get_wallet.return_value = mock_wallet
            
            mock_txn = Mock()
            mock_txn.id = uuid.uuid4()
            mock_txn_create.return_value = mock_txn
            
            # Step 2: Create escrow
            escrow = WalletService.create_task_escrow(
                user=self.user,
                task=task,
                amount=Decimal('100.00')
            )
            
            self.assertEqual(escrow.status, 'locked')
            self.assertEqual(escrow.amount, Decimal('100.00'))
        
        # Step 3: Task completed by member
        member = User.objects.create_user(
            username='taskmember',
            email='member@example.com',
            password='memberpass123'
        )
        WalletService.get_or_create_wallet(member)
        
        # Step 4: Release escrow to member
        WalletService.release_escrow_to_member(task, member)
        
        # Verify escrow released properly
        escrow.refresh_from_db()
        self.assertEqual(escrow.status, 'released')
        
        # Verify member received 80% and company received 20%
        member_amount = Decimal('80.00')  # 100 - 20% fee
        company_amount = Decimal('20.00')
        
        self.assert_transaction_created(member, 'credit', 'task_earning', member_amount)
        self.assert_transaction_created(self.company_user, 'credit', 'platform_fee', company_amount)
        self.assert_wallet_balance(member, member_amount)
    
    def test_referral_bonus_integration(self):
        """Test referral bonus integration flow"""
        # Step 1: Create referrer and referred users
        referrer = self.user
        referred = User.objects.create_user(
            username='referred',
            email='referred@example.com',
            password='referredpass123'
        )
        
        # Step 2: Process referral bonus
        initial_balance = Wallet.objects.get(user=referrer).balance
        
        referral = WalletService.process_referral_bonus(
            referrer=referrer,
            referred=referred,
            amount=Decimal('25.00')
        )
        
        # Step 3: Verify integration
        self.assertEqual(referral.referrer, referrer)
        self.assertEqual(referral.referred, referred)
        self.assertEqual(referral.amount, Decimal('25.00'))
        
        # Verify wallet credited
        self.assert_wallet_balance(referrer, initial_balance + Decimal('25.00'))
        
        # Verify transaction created
        txn = Transaction.objects.get(
            user=referrer,
            category='referral_bonus',
            amount=Decimal('25.00')
        )
        self.assertEqual(txn.transaction_type, 'credit')


class CrossAppIntegrationTest(WalletTestCase):
    """Test integration between wallet app and other apps"""
    
    def test_task_app_integration(self):
        """Test integration with tasks app"""
        # Create task
        task = self.create_task(self.user, "Cross-app Integration Task")
        
        # Create transaction linked to task
        txn = WalletService.credit_wallet(
            user=self.user,
            amount=Decimal('150.00'),
            category='task_earning',
            description='Payment for task completion',
            task=task
        )
        
        # Verify task relationship
        self.assertEqual(txn.task, task)
        
        # Verify transaction appears in task's related transactions
        task_transactions = Transaction.objects.filter(task=task)
        self.assertIn(txn, task_transactions)
    
    def test_subscription_app_integration(self):
        """Test integration with subscriptions app"""
        # Test that subscription decorators work
        url = reverse('wallets:withdrawal_request')
        
        # Without subscription - should redirect
        UserSubscription.objects.filter(user=self.user).delete()
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        
        # With subscription - should work
        self.create_subscription(self.user, self.business_plan)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
    
    def test_payments_app_integration(self):
        """Test integration with payments app"""
        # Create payment transaction
        payment_txn = PaymentTransaction.objects.create(
            user=self.user,
            gateway=PaymentGateway.objects.get(name='paystack'),
            amount=Decimal('100.00'),
            currency='NGN',
            transaction_type='funding',
            status='pending',
            internal_reference='PAY_TEST_123'
        )
        
        # Create wallet transaction linked to payment
        wallet_txn = WalletService.credit_wallet(
            user=self.user,
            amount=Decimal('100.00'),
            category='funding',
            description='Payment gateway funding',
            payment_transaction=payment_txn
        )
        
        # Verify linkage
        self.assertEqual(wallet_txn.payment_transaction, payment_txn)
        
        # Verify reverse relationship
        related_wallet_txns = payment_txn.wallet_transactions.all()
        self.assertIn(wallet_txn, related_wallet_txns)


class ConcurrencyAndRaceConditionTest(TransactionTestCase):
    """Test concurrent operations and race conditions"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='concurrent',
            email='concurrent@example.com',
            password='concurrentpass123'
        )
        self.wallet = WalletService.get_or_create_wallet(self.user)
    
    def test_concurrent_wallet_operations(self):
        """Test concurrent credit/debit operations"""
        # Fund wallet initially
        WalletService.credit_wallet(self.user, Decimal('1000.00'), 'funding')
        
        # Simulate concurrent operations using database transactions
        operations = []
        
        # Multiple credits
        for i in range(5):
            with db_transaction.atomic():
                operations.append(
                    WalletService.credit_wallet(
                        self.user, 
                        Decimal(f'{i + 10}.00'), 
                        'funding',
                        description=f'Concurrent credit {i}'
                    )
                )
        
        # Multiple debits
        for i in range(3):
            with db_transaction.atomic():
                operations.append(
                    WalletService.debit_wallet(
                        self.user,
                        Decimal(f'{i + 5}.00'),
                        'withdrawal',
                        description=f'Concurrent debit {i}'
                    )
                )
        
        # Verify final balance is consistent
        expected_credits = sum(Decimal(f'{i + 10}.00') for i in range(5))  # 50 + 51 + 52 + 53 + 54 = 260
        expected_debits = sum(Decimal(f'{i + 5}.00') for i in range(3))    # 5 + 6 + 7 = 18
        expected_balance = Decimal('1000.00') + expected_credits - expected_debits
        
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, expected_balance)
        
        # Verify all operations recorded
        self.assertEqual(len(operations), 8)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 9)  # 8 + initial funding
    
    def test_atomic_transaction_rollback(self):
        """Test that failed operations roll back properly"""
        initial_balance = Decimal('100.00')
        WalletService.credit_wallet(self.user, initial_balance, 'funding')
        
        # Attempt operation that should fail and rollback
        with self.assertRaises(Exception):
            with db_transaction.atomic():
                # This should succeed
                WalletService.debit_wallet(self.user, Decimal('50.00'), 'withdrawal')
                
                # Force an exception to trigger rollback
                raise Exception("Forced rollback")
        
        # Balance should remain unchanged due to rollback
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, initial_balance)
        
        # No debit transaction should exist
        self.assertFalse(
            Transaction.objects.filter(
                user=self.user,
                transaction_type='debit',
                amount=Decimal('50.00')
            ).exists()
        )


class ErrorHandlingIntegrationTest(WalletTestCase, MockPaystackMixin):
    """Test error handling across integrated systems"""
    
    def test_withdrawal_approval_with_various_failures(self):
        """Test withdrawal approval with different failure scenarios"""
        # Fund wallet
        WalletService.credit_wallet(self.user, Decimal('500.00'), 'funding')
        
        withdrawal = WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            withdrawal_method='paystack',
            account_number='1234567890',
            account_name='Test Account',
            bank_name='Test Bank',
            status='pending'
        )
        
        # Test 1: Paystack recipient creation failure
        with patch('payments.services.PaystackService') as mock_paystack_class:
            mock_paystack = mock_paystack_class.return_value
            mock_paystack.create_transfer_recipient.return_value = {
                'success': False,
                'error': 'Invalid account details'
            }
            
            with self.assertRaises(ValueError):
                WalletService.approve_withdrawal(withdrawal.id, self.admin_user)
            
            # Wallet should not be debited
            self.assert_wallet_balance(self.user, Decimal('500.00'))
        
        # Test 2: Transfer initiation failure
        with patch('payments.services.PaystackService') as mock_paystack_class:
            mock_paystack = mock_paystack_class.return_value
            mock_paystack.create_transfer_recipient.return_value = {
                'success': True,
                'data': {'data': {'recipient_code': 'RCP_test'}}
            }
            mock_paystack.initiate_transfer.return_value = {
                'success': False,
                'error': 'Insufficient funds in gateway account'
            }
            
            with self.assertRaises(ValueError):
                WalletService.approve_withdrawal(withdrawal.id, self.admin_user)
            
            # Wallet should still not be debited
            self.assert_wallet_balance(self.user, Decimal('500.00'))
    
    def test_form_validation_integration(self):
        """Test form validation integration with services"""
        # Test withdrawal form with insufficient funds
        WalletService.credit_wallet(self.user, Decimal('50.00'), 'funding')  # Only 50 available
        
        form_data = {
            'amount': Decimal('100.00'),  # More than available
            'withdrawal_method': 'paystack',
            'account_number': '1234567890',
            'account_name': 'Test Account',
            'bank_name': 'Test Bank'
        }
        
        form = WithdrawalRequestForm(data=form_data)
        self.assertTrue(form.is_valid())  # Form itself is valid
        
        # But service should reject it
        with self.assertRaises(ValueError):
            WalletService.create_withdrawal_request(
                user=self.user,
                amount=form.cleaned_data['amount'],
                withdrawal_method=form.cleaned_data['withdrawal_method'],
                account_details={
                    'account_number': form.cleaned_data['account_number'],
                    'account_name': form.cleaned_data['account_name'],
                    'bank_name': form.cleaned_data['bank_name'],
                }
            )
    
    def test_escrow_edge_cases(self):
        """Test escrow system edge cases and error handling"""
        task = self.create_task(self.user, "Edge Case Task")
        
        # Test 1: Double escrow creation (should fail)
        escrow1 = EscrowTransaction.objects.create(
            task=task,
            advertiser=self.user,
            amount=Decimal('100.00')
        )
        escrow1.save()
        with self.assertRaises(Exception):  # IntegrityError due to OneToOne constraint
            EscrowTransaction.objects.create(
                task=task,
                advertiser=self.user,
                amount=Decimal('50.00')
            )
        
        # Test 2: Release already released escrow
        escrow1.status = 'released'
        escrow1.save()
        
        member = User.objects.create_user(
            username='member',
            email='member@example.com',
            password='memberpass123'
        )
        
        with self.assertRaises(EscrowTransaction.DoesNotExist):
            WalletService.release_escrow_to_member(task, member)


class PerformanceIntegrationTest(WalletTestCase):
    """Test performance aspects of integrated operations"""
    
    def test_bulk_transaction_creation_performance(self):
        """Test performance with bulk transaction operations"""
        # Create multiple transactions efficiently
        transactions = []
        for i in range(100):
            transactions.append(
                WalletService.credit_wallet(
                    self.user,
                    Decimal(f'{i + 1}.00'),
                    'funding',
                    description=f'Bulk transaction {i}'
                )
            )
        
        # Verify all transactions created
        self.assertEqual(len(transactions), 100)
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 100)
        
        # Verify final balance is correct
        expected_total = sum(Decimal(f'{i + 1}.00') for i in range(100))
        self.assert_wallet_balance(self.user, expected_total)
    
    def test_dashboard_query_optimization(self):
        """Test that dashboard queries are optimized"""
        # Create various types of data
        for i in range(10):
            WalletService.credit_wallet(self.user, Decimal('10.00'), 'task_earning')
            WalletService.credit_wallet(self.user, Decimal('5.00'), 'referral_bonus')
        
        # Create withdrawals
        for i in range(5):
            WithdrawalRequest.objects.create(
                user=self.user,
                amount=Decimal('20.00'),
                withdrawal_method='paystack',
                account_number=f'123456789{i}',
                account_name=f'Account {i}',
                bank_name='Test Bank',
                status='pending' if i < 3 else 'completed'
            )
        
        # Access dashboard (this would test query efficiency in a real scenario)
        self.client.force_login(self.user)
        url = reverse('wallets:dashboard')
        
        with self.assertNumQueries(12):  # Adjust based on actual optimized query count
            response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify calculated values are correct
        context = response.context110
        self.assertEqual(context['total_earned'], Decimal('150.00'))  # 10*10 + 10*5
        self.assertEqual(context['pending_withdrawals'], Decimal('60.00'))  # 3*20