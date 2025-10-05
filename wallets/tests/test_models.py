# wallets/tests/test_models.py
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from decimal import Decimal
import uuid

from ..models import Wallet, Transaction, WithdrawalRequest, EscrowTransaction
from .test_base import BaseWalletTestCase

User = get_user_model()


class WalletModelTest(BaseWalletTestCase):
    """Test Wallet model functionality"""

    def test_wallet_creation(self):
        """Test wallet creation with default values"""
        self.assertEqual(self.wallet.user, self.user)
        self.assertEqual(self.wallet.balance, Decimal('0.00'))
        self.assertIsNotNone(self.wallet.created_at)
        self.assertIsNotNone(self.wallet.updated_at)

    def test_wallet_str_representation(self):
        """Test wallet string representation"""
        expected = f"{self.user.username} - $0.00"
        self.assertEqual(str(self.wallet), expected)

        # Test with non-zero balance
        self.wallet.balance = Decimal('150.50')
        self.wallet.save()
        expected = f"{self.user.username} - $150.50"
        self.assertEqual(str(self.wallet), expected)

    def test_one_to_one_relationship(self):
        """Test that each user has only one wallet"""
        with self.assertRaises(IntegrityError):
            Wallet.objects.create(user=self.user, balance=Decimal('100.00'))

    def test_get_available_balance(self):
        """Test get_available_balance method"""
        self.wallet.balance = Decimal('100.00')
        self.wallet.save()
        self.assertEqual(self.wallet.get_available_balance(), Decimal('100.00'))

    def test_get_display_balance_no_pending_withdrawals(self):
        """Test get_display_balance with no pending withdrawals"""
        self.wallet.balance = Decimal('100.00')
        self.wallet.save()
        self.assertEqual(self.wallet.get_display_balance(), Decimal('100.00'))

    def test_get_display_balance_with_pending_withdrawals(self):
        """Test get_display_balance with pending withdrawals"""
        self.wallet.balance = Decimal('100.00')
        self.wallet.save()

        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('30.00'),
            withdrawal_method='paystack',
            status='pending'  # optional fields omitted
        )
        self.assertEqual(self.wallet.get_display_balance(), Decimal('70.00'))

    def test_get_pending_withdrawals(self):
        """Test get_pending_withdrawals method"""
        self.assertEqual(self.wallet.get_pending_withdrawals(), Decimal('0.00'))

        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('25.00'),
            withdrawal_method='paystack',
            status='pending'
        )
        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('15.00'),
            withdrawal_method='bank_transfer',
            status='pending'
        )
        self.assertEqual(self.wallet.get_pending_withdrawals(), Decimal('40.00'))

        # Completed withdrawal should not count
        WithdrawalRequest.objects.create(
            user=self.user,
            amount=Decimal('10.00'),
            withdrawal_method='paystack',
            status='completed'
        )
        self.assertEqual(self.wallet.get_pending_withdrawals(), Decimal('40.00'))


class TransactionModelTest(BaseWalletTestCase):
    """Test Transaction model functionality"""

    def test_transaction_creation(self):
        transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('50.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50.00'),
            description='Test funding',
            reference="REF123"
        )
        self.assertEqual(transaction.reference, "REF123")
        self.assertEqual(transaction.status, 'pending')
        self.assertIsInstance(transaction.id, uuid.UUID)

    def test_transaction_str_representation(self):
        transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='debit',
            category='withdrawal',
            amount=Decimal('25.50'),
            balance_before=Decimal('100.00'),
            balance_after=Decimal('74.50')
        )
        expected = f"{self.user.username} - debit $25.50 (withdrawal)"
        self.assertEqual(str(transaction), expected)

    def test_transaction_ordering(self):
        txn1 = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('10.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('10.00')
        )
        txn2 = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('20.00'),
            balance_before=Decimal('10.00'),
            balance_after=Decimal('30.00')
        )
        transactions = Transaction.objects.filter(user=self.user)
        self.assertEqual(transactions.first(), txn2)
        self.assertEqual(transactions.last(), txn1)

    def test_transaction_choices_validation(self):
        with self.assertRaises(ValidationError):
            Transaction(
                user=self.user,
                transaction_type='invalid_type',
                category='funding',
                amount=Decimal('50.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('50.00')
            ).full_clean()

        with self.assertRaises(ValidationError):
            Transaction(
                user=self.user,
                transaction_type='credit',
                category='invalid_category',
                amount=Decimal('50.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('50.00')
            ).full_clean()

        with self.assertRaises(ValidationError):
            Transaction(
                user=self.user,
                transaction_type='credit',
                category='funding',
                amount=Decimal('50.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('50.00'),
                status='invalid_status'
            ).full_clean()

    def test_minimum_amount_validation(self):
        with self.assertRaises(ValidationError):
            Transaction(
                user=self.user,
                transaction_type='credit',
                category='funding',
                amount=Decimal('0.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('0.00')
            ).full_clean()

    def test_related_transaction_relationship(self):
        original_txn = Transaction.objects.create(
            user=self.user,
            transaction_type='debit',
            category='escrow',
            amount=Decimal('50.00'),
            balance_before=Decimal('100.00'),
            balance_after=Decimal('50.00')
        )
        related_txn = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='escrow_release',
            amount=Decimal('50.00'),
            balance_before=Decimal('50.00'),
            balance_after=Decimal('100.00'),
            related_transaction=original_txn
        )
        self.assertEqual(related_txn.related_transaction, original_txn)


class WithdrawalRequestModelTest(BaseWalletTestCase):
    """Test WithdrawalRequest model functionality"""

    def setUp(self):
        super().setUp()
        self.withdrawal_data = {
            'user': self.user,
            'amount': Decimal('100.00'),
            'withdrawal_method': 'paystack',
        }

    def test_withdrawal_request_creation(self):
        withdrawal = WithdrawalRequest.objects.create(**self.withdrawal_data)
        self.assertEqual(withdrawal.status, 'pending')
        self.assertIsInstance(withdrawal.id, uuid.UUID)

    def test_withdrawal_request_str_representation(self):
        withdrawal = WithdrawalRequest.objects.create(**self.withdrawal_data)
        expected = f"{self.user.username} - $100.00 (pending)"
        self.assertEqual(str(withdrawal), expected)
        withdrawal.status = 'completed'
        withdrawal.save()
        expected = f"{self.user.username} - $100.00 (completed)"
        self.assertEqual(str(withdrawal), expected)

    def test_withdrawal_request_ordering(self):
        WithdrawalRequest.objects.create(**self.withdrawal_data)
        withdrawal2 = WithdrawalRequest.objects.create(
            user=self.user, withdrawal_method='paystack', amount=Decimal('200.00')
        )

        withdrawals = WithdrawalRequest.objects.filter(user=self.user)
        self.assertEqual(withdrawals.first(), withdrawal2)

    def test_minimum_amount_validation(self):
        with self.assertRaises(ValidationError):
            WithdrawalRequest(
                user=self.user, amount=Decimal('0.50'), withdrawal_method='paystack'
            ).full_clean()

    def test_withdrawal_method_choices(self):
        for method in ['paystack', 'flutterwave', 'bank_transfer', 'crypto']:
            WithdrawalRequest(
                user=self.user, amount=Decimal('100.00'), withdrawal_method=method
            ).full_clean()
        with self.assertRaises(ValidationError):
            WithdrawalRequest(
                user=self.user, amount=Decimal('100.00'), withdrawal_method='invalid'
            ).full_clean()

    def test_optional_fields(self):
        withdrawal = WithdrawalRequest.objects.create(**self.withdrawal_data)
        self.assertEqual(withdrawal.account_number, '')
        self.assertEqual(withdrawal.bank_name, '')

    def test_gateway_response_field(self):
        withdrawal = WithdrawalRequest.objects.create(
            **self.withdrawal_data, gateway_response={"status": "ok"}
        )
        self.assertEqual(withdrawal.gateway_response["status"], "ok")

    def test_processed_by_relationship(self):
        withdrawal = WithdrawalRequest.objects.create(**self.withdrawal_data)
        self.assertIsNone(withdrawal.processed_by)
        withdrawal.processed_by = self.admin_user
        withdrawal.save()
        self.assertEqual(withdrawal.processed_by, self.admin_user)


class EscrowTransactionModelTest(BaseWalletTestCase):
    """Test EscrowTransaction model functionality"""

    def setUp(self):
        super().setUp()
        self.task = self.create_task(self.user, "Test Task", Decimal('100.00'))

    def test_escrow_transaction_creation(self):
        escrow = EscrowTransaction.objects.create(
            task=self.task, advertiser=self.user, amount=Decimal('100.00')
        )
        self.assertEqual(escrow.status, 'locked')
        self.assertIsNone(escrow.released_at)

    def test_escrow_transaction_str_representation(self):
        escrow = EscrowTransaction.objects.create(
            task=self.task, advertiser=self.user, amount=Decimal('75.50')
        )
        expected = f"Escrow for Task #{self.task.id} - $75.50"
        self.assertEqual(str(escrow), expected)

    def test_one_to_one_task_relationship(self):
        EscrowTransaction.objects.create(
            task=self.task, advertiser=self.user, amount=Decimal('100.00')
        )
        with self.assertRaises(IntegrityError):
            EscrowTransaction.objects.create(
                task=self.task, advertiser=self.user, amount=Decimal('50.00')
            )

    def test_escrow_status_choices(self):
        for status in ['locked', 'released', 'refunded']:
            EscrowTransaction(
                task=self.task, advertiser=self.user, amount=Decimal('100.00'), status=status
            ).full_clean()
        with self.assertRaises(ValidationError):
            EscrowTransaction(
                task=self.task, advertiser=self.user, amount=Decimal('100.00'), status='invalid'
            ).full_clean()

    def test_taskwallet_transaction_nullable(self):
        escrow = EscrowTransaction.objects.create(
            task=self.task, advertiser=self.user, amount=Decimal('100.00'),
            taskwallet_transaction=None
        )
        self.assertIsNone(escrow.taskwallet_transaction)


class ModelRelationshipTest(BaseWalletTestCase):
    """Test model relationships and constraints"""

    def test_user_wallet_relationship(self):
        self.assertEqual(self.user.wallet, self.wallet)
        self.assertEqual(self.wallet.user, self.user)

    def test_user_transaction_relationship(self):
        txn1 = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('50.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50.00')
        )
        txn2 = Transaction.objects.create(
            user=self.user,
            transaction_type='debit',
            category='withdrawal',
            amount=Decimal('25.00'),
            balance_before=Decimal('50.00'),
            balance_after=Decimal('25.00')
        )
        user_transactions = self.user.transactions.all()
        self.assertIn(txn1, user_transactions)
        self.assertIn(txn2, user_transactions)

    def test_user_withdrawal_relationship(self):
        withdrawal1 = WithdrawalRequest.objects.create(
            user=self.user, amount=Decimal('100.00'), withdrawal_method='paystack'
        )
        withdrawal2 = WithdrawalRequest.objects.create(
            user=self.user, amount=Decimal('200.00'), withdrawal_method='bank_transfer'
        )
        user_withdrawals = self.user.withdrawals.all()
        self.assertIn(withdrawal1, user_withdrawals)
        self.assertIn(withdrawal2, user_withdrawals)

    def test_transaction_task_relationship(self):
        task = self.create_task(self.user, "Test Task")
        transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='task_earning',
            amount=Decimal('50.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50.00'),
            task=task
        )
        self.assertEqual(transaction.task, task)

    def test_model_uuid_primary_keys(self):
        transaction = Transaction.objects.create(
            user=self.user,
            transaction_type='credit',
            category='funding',
            amount=Decimal('50.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50.00')
        )
        withdrawal = WithdrawalRequest.objects.create(
            user=self.user, amount=Decimal('100.00'), withdrawal_method='paystack'
        )
        self.assertIsInstance(transaction.id, uuid.UUID)
        self.assertIsInstance(withdrawal.id, uuid.UUID)
        self.assertNotEqual(transaction.id, withdrawal.id)

    def test_decimal_field_precision(self):
        large_amount = Decimal('99999999.99')  # fits within 12 digits
        wallet = Wallet.objects.get(user=self.other_user)
        wallet.balance = large_amount
        wallet.save()
        self.assertEqual(wallet.balance, large_amount)

    def test_model_field_constraints(self):
        with self.assertRaises(ValidationError):
            WithdrawalRequest(
                user=self.user, amount=Decimal('100.00'),
                withdrawal_method='paystack', account_number='1' * 25
            ).full_clean()
