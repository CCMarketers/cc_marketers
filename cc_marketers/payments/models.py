# payments/models.py
from django.db import models
from django.conf import settings  
from django.utils import timezone
import uuid


class PaymentGateway(models.Model):
    """Model to store different payment gateways"""
    name = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict)  # Store gateway-specific config
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'payment_gateways'


class PaymentTransaction(models.Model):
    """Model to track all payment transactions"""
    
    class TransactionType(models.TextChoices):
        FUNDING = 'funding', 'Funding'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
    
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ✅ Use AUTH_USER_MODEL instead of User
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_transactions'
    )
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)
    
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    
    # Gateway-specific reference
    gateway_reference = models.CharField(max_length=255, unique=True)
    internal_reference = models.CharField(max_length=100, unique=True, blank=True)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    
    # Metadata
    gateway_response = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.internal_reference:
            self.internal_reference = f"TXN_{timezone.now().strftime('%Y%m%d%H%M%S')}_{str(self.id)[:8]}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.transaction_type.title()} - {self.user} - {self.amount} {self.currency}"
    
    class Meta:
        db_table = 'payment_transactions'
        ordering = ['-created_at']


class PaystackTransaction(models.Model):
    """Paystack-specific transaction details"""
    transaction = models.OneToOneField(
        PaymentTransaction, 
        on_delete=models.CASCADE, 
        related_name='paystack_details'
    )
    
    # Paystack specific fields
    authorization_url = models.URLField(blank=True)
    access_code = models.CharField(max_length=255, blank=True)
    paystack_reference = models.CharField(max_length=255, unique=True)
    
    # For withdrawals
    recipient_code = models.CharField(max_length=255, blank=True)
    transfer_code = models.CharField(max_length=255, blank=True)
    
    # Bank details for withdrawals
    bank_code = models.CharField(max_length=10, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=255, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Paystack - {self.paystack_reference}"
    
    class Meta:
        db_table = 'paystack_transactions'


class WebhookEvent(models.Model):
    """Store webhook events for auditing and debugging"""
    
    class EventType(models.TextChoices):
        CHARGE_SUCCESS = 'charge.success', 'Charge Success'
        TRANSFER_SUCCESS = 'transfer.success', 'Transfer Success'
        TRANSFER_FAILED = 'transfer.failed', 'Transfer Failed'
        OTHER = 'other', 'Other'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    
    reference = models.CharField(max_length=255, db_index=True)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.gateway.name} - {self.event_type} - {self.reference}"
    
    class Meta:
        db_table = 'webhook_events'
        ordering = ['-created_at']