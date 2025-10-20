from decimal import Decimal
import uuid
from django.db.models import Sum
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from payments.models import PaymentTransaction


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
        """Sum of all pending withdrawals in ₦."""
        total = (
            WithdrawalRequest.objects.filter(user=self.user, status="pending")
            .aggregate(total=Sum("amount_usd"))["total"]
            or Decimal("0.00")
        )
        return total

    def available_balance(self) -> Decimal:
        """Amount the user can actually spend right now (₦)."""
        available = self.balance - self.get_pending_withdrawals()
        return available if available > 0 else Decimal("0.00")

    def get_available_balance(self) -> Decimal:
        """Alias for clarity."""
        return self.available_balance()


class EscrowTransaction(models.Model):
    """Tracks funds locked in escrow for tasks (₦)."""
    task = models.OneToOneField('tasks.Task', on_delete=models.CASCADE)
    advertiser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="escrow_transaction"
    )
    amount_usd = models.DecimalField(max_digits=12, decimal_places=2)  # ₦ equivalent
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

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

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
        ('bank_transfer', 'Bank Transfer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="withdrawals"
    )
    amount_usd = models.DecimalField(  # ₦ equivalent
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('1.00'))]
    )
    withdrawal_method = models.CharField(max_length=20, choices=WITHDRAWAL_METHODS)

    account_number = models.CharField(max_length=20, blank=True, null=True)
    account_name = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=10, blank=True, null=True)

    status = models.CharField(max_length=10, choices=WITHDRAWAL_STATUS, default='pending')
    admin_notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='processed_withdrawals'
    )

    gateway_reference = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(blank=True, null=True)

    transaction = models.ForeignKey(PaymentTransaction, on_delete=models.CASCADE, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at', '-processed_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{getattr(self.user, 'username', self.user.id)} - ₦{self.amount_usd:,.2f} ({self.status})"
