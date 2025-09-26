from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    def __str__(self):
        return f"{getattr(self.user, 'username', self.user.id)} - ₦{self.balance:,.2f}"

    def get_pending_withdrawals(self) -> Decimal:
        """
        Total amount currently pending for withdrawal.
        Always returns a Decimal (0.00 if none).
        """
        pending = WithdrawalRequest.objects.filter(
            user=self.user, status='pending'
        ).aggregate(total=Sum('amount_usd'))['total']
        return pending or Decimal('0.00')

    def get_available_balance(self) -> Decimal:
        """
        Balance minus any pending withdrawals.
        """
        return self.balance - self.get_pending_withdrawals()

    def get_display_balance(self) -> Decimal:
        """
        Alias for available balance.
        """
        return self.get_available_balance()


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]
    TRANSACTION_CATEGORIES = [
        ('task_payment', 'Task Payment'),
        ('task_earning', 'Task Earning'),
        ('referral_bonus', 'Referral Bonus'),
        ('withdrawal', 'Withdrawal'),
        ('funding', 'Funding'),
        ('escrow', 'Escrow'),
        ('escrow_release', 'Escrow Release'),
        ('refund', 'Refund'),
        ('admin_adjustment', 'Admin Adjustment'),
        ('company_cut', 'Company Cut'),
    ]
    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions"
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    category = models.CharField(max_length=20, choices=TRANSACTION_CATEGORIES)
    amount_usd = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=TRANSACTION_STATUS, default='pending')
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True)
    # amount_usd = models.DecimalField(max_digits=15, decimal_places=2, default='0.0')
    amount_local = models.DecimalField(max_digits=15, decimal_places=2, default='0.0')
    currency = models.CharField(max_length=3, default='USD')

    payment_transaction = models.ForeignKey(
        'payments.PaymentTransaction',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='wallet_transactions'
    )

    # Related objects
    task = models.ForeignKey('tasks.Task', on_delete=models.CASCADE, blank=True, null=True)
    related_transaction = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-updated_at']

    def __str__(self):
        return (
            f"{getattr(self.user, 'username', self.user.id)} "
            f"- {self.transaction_type} ₦{self.amount_usd:,.2f} ({self.category})"
        )


class EscrowTransaction(models.Model):
    """Tracks funds locked in escrow for tasks."""
    task = models.OneToOneField('tasks.Task', on_delete=models.CASCADE)
    advertiser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="escrow_transaction"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    taskwallet_transaction = models.ForeignKey(
        'tasks.TaskWalletTransaction',
        on_delete=models.CASCADE,
        related_name="escrow_transactions",
        null=True, blank=True
    )
    status = models.CharField(
        max_length=10,
        choices=[
            ('locked', 'Locked'),
            ('released', 'Released'),
            ('refunded', 'Refunded'),
        ],
        default='locked'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Escrow for Task #{self.task.id} - ₦{self.amount:,.2f}"


class WithdrawalRequest(models.Model):
    WITHDRAWAL_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    WITHDRAWAL_METHODS = [
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave'),
        ('crypto', 'Crypto'),
        ('bank_transfer', 'Bank Transfer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="withdrawals"
    )
    amount_usd = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('1.00'))]
    )
    withdrawal_method = models.CharField(max_length=20, choices=WITHDRAWAL_METHODS)

    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100)
    bank_code = models.CharField(max_length=10, blank=True)

    status = models.CharField(max_length=10, choices=WITHDRAWAL_STATUS, default='pending')
    admin_notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='processed_withdrawals'
    )

    # Payment gateway response
    gateway_reference = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at', '-processed_at']

    def __str__(self):
        return f"{getattr(self.user, 'username', self.user.id)} - ₦{self.amount:,.2f} ({self.status})"
