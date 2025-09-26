import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class PaymentGateway(models.Model):
    """
    Stores configuration for each payment gateway (e.g., Paystack, Flutterwave).
    """
    name = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)  # gateway-specific config
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_gateways"
        verbose_name = "Payment Gateway"
        verbose_name_plural = "Payment Gateways"

    def __str__(self) -> str:
        return self.name


class PaymentTransaction(models.Model):
    """
    Tracks all inflow/outflow transactions, regardless of gateway.
    """

    class TransactionType(models.TextChoices):
        FUNDING = "funding", "Funding"
        WITHDRAWAL = "withdrawal", "Withdrawal"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_transactions",
    )
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)

    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")

    gateway_reference = models.CharField(max_length=255, unique=True, db_index=True)
    internal_reference = models.CharField(max_length=100, unique=True, blank=True, db_index=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Raw gateway responses & arbitrary metadata
    gateway_response = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payment_transactions"
        ordering = ["-created_at"]
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions"

    def __str__(self) -> str:
        return f"{self.transaction_type.title()} - {self.user} - {self.amount} {self.currency}"

    def _generate_internal_reference(self) -> str:
        """Generate a predictable internal reference once per transaction."""
        return f"TXN_{timezone.now().strftime('%Y%m%d%H%M%S')}_{str(self.id)[:8]}"

    def save(self, *args, **kwargs):
        if not self.internal_reference:
            self.internal_reference = self._generate_internal_reference()
        super().save(*args, **kwargs)


class PaystackTransaction(models.Model):
    """
    Holds Paystack-specific fields linked to a generic PaymentTransaction.
    """
    transaction = models.OneToOneField(
        PaymentTransaction,
        on_delete=models.CASCADE,
        related_name="paystack_details",
    )

    # Paystack checkout data
    authorization_url = models.URLField(blank=True)
    access_code = models.CharField(max_length=255, blank=True)
    paystack_reference = models.CharField(max_length=255, unique=True, db_index=True)

    # Withdrawal / transfer data
    recipient_code = models.CharField(max_length=255, blank=True)
    transfer_code = models.CharField(max_length=255, blank=True)

    # Bank details (for withdrawals)
    bank_code = models.CharField(max_length=10, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "paystack_transactions"
        verbose_name = "Paystack Transaction"
        verbose_name_plural = "Paystack Transactions"

    def __str__(self) -> str:
        return f"Paystack - {self.paystack_reference}"


class WebhookEvent(models.Model):
    """
    Stores raw webhook events for auditing and debugging. One row per event.
    """

    class EventType(models.TextChoices):
        CHARGE_SUCCESS = "charge.success", "Charge Success"
        TRANSFER_SUCCESS = "transfer.success", "Transfer Success"
        TRANSFER_FAILED = "transfer.failed", "Transfer Failed"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=50, choices=EventType.choices)

    reference = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "webhook_events"
        ordering = ["-created_at"]
        verbose_name = "Webhook Event"
        verbose_name_plural = "Webhook Events"

    def __str__(self) -> str:
        return f"{self.gateway.name} - {self.event_type} - {self.reference}"

class FlutterwaveTransaction(models.Model):
    """
    Holds Flutterwave-specific fields linked to a generic PaymentTransaction.
    """
    transaction = models.OneToOneField(
        PaymentTransaction,
        on_delete=models.CASCADE,
        related_name="flutterwave_details",
    )

    # Flutterwave payment data
    payment_link = models.URLField(blank=True)
    flutterwave_id = models.CharField(max_length=255, blank=True)  # Flutterwave transaction ID
    flutterwave_reference = models.CharField(max_length=255, unique=True, db_index=True)
    
    # Transfer/withdrawal data
    transfer_id = models.CharField(max_length=255, blank=True)
    beneficiary_id = models.CharField(max_length=255, blank=True)

    # Bank details (for withdrawals)
    bank_code = models.CharField(max_length=10, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "flutterwave_transactions"
        verbose_name = "Flutterwave Transaction"
        verbose_name_plural = "Flutterwave Transactions"

    def __str__(self) -> str:
        return f"Flutterwave - {self.flutterwave_reference}"


class CurrencyRate(models.Model):
    base_currency = models.CharField(max_length=3, default='USD')
    target_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=10, decimal_places=4)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['base_currency', 'target_currency']

    def __str__(self):
        return f"{self.base_currency} → {self.target_currency}: {self.rate}"
