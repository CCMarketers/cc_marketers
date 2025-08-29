from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.db.models import Sum
import uuid


class Wallet(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - ${self.balance}"

    def get_available_balance(self):
        """Just return actual wallet balance (escrow already deducted during debit)."""
        return self.balance

    def get_display_balance(self):
        """Balance minus pending withdrawals."""
        return self.balance - self.get_pending_withdrawals()

    
    def get_pending_withdrawals(self):
        return self.withdrawalrequest_set.filter(
            status='pending'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')



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
        ('escrow', 'Escrow'),
        ('escrow_release', 'Escrow Release'),
        ('refund', 'Refund'),
        ('admin_adjustment', 'Admin Adjustment'),
        ('company_cut', 'company_cut'),
    ]

    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    category = models.CharField(max_length=20, choices=TRANSACTION_CATEGORIES)
    amount = models.DecimalField(max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(Decimal('0.01'))])
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=TRANSACTION_STATUS, default='pending')
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True)

    # Related objects
    task = models.ForeignKey('tasks.Task', on_delete=models.CASCADE, blank=True, null=True)
    related_transaction = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} ${self.amount} ({self.category})"


class EscrowTransaction(models.Model):
    """Tracks funds locked in escrow for tasks"""
    task = models.OneToOneField('tasks.Task', on_delete=models.CASCADE)
    advertiser = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    taskwallet_transaction = models.ForeignKey(
        'tasks.TaskWalletTransaction',
        on_delete=models.CASCADE,
        related_name="escrow_transactions",
        null=True, blank=True
    )
    status = models.CharField(max_length=10, choices=[
        ('locked', 'Locked'),
        ('released', 'Released'),
        ('refunded', 'Refunded'),
    ], default='locked')
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Escrow for Task #{self.task.id} - ${self.amount}"


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
        ('bank_transfer', 'Bank Transfer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2,
                                 validators=[MinValueValidator(Decimal('1.00'))])
    withdrawal_method = models.CharField(max_length=20, choices=WITHDRAWAL_METHODS)

    # Bank details
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_code = models.CharField(max_length=10, blank=True)

    status = models.CharField(max_length=10, choices=WITHDRAWAL_STATUS, default='pending')
    admin_notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='processed_withdrawals'
    )

    # Payment gateway response
    gateway_reference = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - ${self.amount} ({self.status})"


