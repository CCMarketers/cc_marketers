# referrals/models.py
import logging
import random
import string
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from wallets.models import Wallet
from payments.models import PaymentTransaction

logger = logging.getLogger(__name__)

User = get_user_model()


class ReferralCode(models.Model):
    """Unique referral code assigned to each user."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="referral_code")
    code = models.CharField(max_length=10, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        """Generate a unique referral code (8 chars upper/digit)."""
        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not ReferralCode.objects.filter(code=code).exists():
                return code

    def __str__(self):
        return f"{self.user.get_display_name()} - {self.code}"


class Referral(models.Model):
    """Tracks referrals and their relationship levels."""
    LEVEL_CHOICES = [
        (1, "Direct (Level 1)"),
        (2, "Indirect (Level 2)"),
        (3, "Level 3"),
    ]

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_made"
    )
    referred = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_source"
    )
    level = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES, default=1)
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["referrer", "referred", "level"]
        indexes = [
            models.Index(fields=["referrer", "level"]),
        ]

    def __str__(self):
        return f"{self.referrer} → {self.referred} (Level {self.level})"


class ReferralEarning(models.Model):
    """Tracks earnings generated from referrals."""
    EARNING_TYPES = [
        ("signup", "New Signup"),
        ("task_completion", "Task Completion"),
        ("advertiser_funding", "Advertiser Funding"),
        ("subscription", "Subscription Purchase"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_earnings"
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="earnings_generated"
    )
    referral = models.ForeignKey("Referral", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    earning_type = models.CharField(max_length=20, choices=EARNING_TYPES)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)  # percentage
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="approved")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["referrer", "status"]),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new and self.status == "approved":
            self.approved_at = timezone.now()
        super().save(*args, **kwargs)
        if is_new and self.status == "approved":
            self._credit_wallet()

    def approve(self):
        """Instantly approve and credit."""
        self.status = "approved"
        self.approved_at = timezone.now()
        self.save()

    @transaction.atomic
    def _credit_wallet(self):
        """Credit referral bonus into wallet."""
        ref = f"REFERRAL_{self.id}"
        if PaymentTransaction.objects.filter(reference=ref).exists():
            logger.debug("Referral %s already credited", self.id)
            return

        wallet, _ = Wallet.objects.select_for_update().get_or_create(user=self.referrer)
        balance_before = wallet.balance
        balance_after = balance_before + Decimal(self.amount)

        tx = PaymentTransaction.objects.create(
            user=self.referrer,
            transaction_type="funding",
            category="referral_bonus",
            amount_usd=self.amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status="success",
            reference=ref,
            description=f"Referral earning from {self.referred_user.username}",
        )
        self.transaction_id = str(tx.id)
        super().save(update_fields=["transaction_id"])

        wallet.balance = balance_after
        wallet.save(update_fields=["balance"])


class CommissionTier(models.Model):
    """Defines commission rates per referral level and earning type."""
    level = models.PositiveSmallIntegerField()
    rate = models.DecimalField(max_digits=5, decimal_places=2)  # percentage
    earning_type = models.CharField(max_length=20, choices=ReferralEarning.EARNING_TYPES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["level", "earning_type"]
        indexes = [
            models.Index(fields=["level", "earning_type"]),
        ]

    def __str__(self):
        return f"Level {self.level} - {self.rate}% for {self.earning_type}"
