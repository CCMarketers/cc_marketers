
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
    can_refer = models.BooleanField(default=True, help_text="Can this user create new referrals?")

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
            logger.info(f"[REFERRAL_CODE] Generated new code: {self.code} for user: {self.user.username}")
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        """Generate a unique referral code (8 chars upper/digit)."""
        attempts = 0
        max_attempts = 10
        
        while attempts < max_attempts:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not ReferralCode.objects.filter(code=code).exists():
                logger.debug(f"[REFERRAL_CODE] Successfully generated unique code: {code} after {attempts + 1} attempts")
                return code
            attempts += 1
        
        logger.error(f"[REFERRAL_CODE] Failed to generate unique code after {max_attempts} attempts")
        raise ValueError("Unable to generate unique referral code")

    def get_active_demo_referral_count(self):
        """Count currently active Demo referrals (for Business members' 10-slot limit)."""
        from subscriptions.services import SubscriptionService
        
        logger.debug(f"[REFERRAL_COUNT] Counting active Demo referrals for user: {self.user.username}")
        
        count = 0
        referrals = Referral.objects.filter(
            referrer=self.user,
            level=1,
            is_active=True
        ).select_related('referred')
        
        for ref in referrals:
            user_sub = SubscriptionService.get_user_active_subscription(ref.referred)
            if user_sub and user_sub.plan.name == "Demo Account":
                count += 1
                logger.debug(f"[REFERRAL_COUNT] Counted Demo user: {ref.referred.username}")
        
        logger.info(f"[REFERRAL_COUNT] User {self.user.username} has {count} active Demo referrals")
        return count

    def __str__(self):
        return f"{self.user.get_display_name()} - {self.code}"


class Referral(models.Model):
    """Tracks referrals and their relationship levels (max 2 levels)."""
    LEVEL_CHOICES = [
        (1, "Direct (Level 1)"),
        (2, "Indirect (Level 2)"),
    ]

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_made"
    )
    referred = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referral_source"
    )
    level = models.PositiveSmallIntegerField(choices=LEVEL_CHOICES, default=1)
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE)
    
    # Snapshot of subscription types at creation
    referrer_subscription_type = models.CharField(max_length=50, blank=True)
    referred_subscription_type = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_within_limits = models.BooleanField(
        default=True, 
        help_text="Was this referral within the Demo limit when created?"
    )

    class Meta:
        unique_together = ["referrer", "referred", "level"]
        indexes = [
            models.Index(fields=["referrer", "level"]),
            models.Index(fields=["referred"]),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            logger.info(
                f"[REFERRAL_CREATE] Creating referral: {self.referrer.username} → "
                f"{self.referred.username} (Level {self.level}, "
                f"{self.referrer_subscription_type} → {self.referred_subscription_type})"
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.referrer} → {self.referred} (Level {self.level})"


class ReferralEarning(models.Model):
    """Tracks earnings generated from referrals (Business signups only)."""
    EARNING_TYPES = [
        ("signup", "New Business Signup"),
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
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="approved")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["referrer", "status"]),
            models.Index(fields=["referred_user", "earning_type"]),
        ]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            logger.info(
                f"[EARNING_CREATE] Creating earning: {self.referrer.username} earns "
                f"₦{self.amount} from {self.referred_user.username} ({self.earning_type}, "
                f"Level {self.referral.level}, Status: {self.status})"
            )
            if self.status == "approved":
                self.approved_at = timezone.now()
        
        super().save(*args, **kwargs)
        
        if is_new and self.status == "approved":
            logger.info(f"[EARNING_CREDIT] Initiating wallet credit for earning ID: {self.pk}")
            self._credit_wallet()

    def approve(self):
        """Instantly approve and credit."""
        logger.info(f"[EARNING_APPROVE] Approving earning ID: {self.pk} for {self.referrer.username}")
        self.status = "approved"
        self.approved_at = timezone.now()
        self.save()

    @transaction.atomic
    def _credit_wallet(self):
        """Credit referral bonus into wallet."""
        ref = f"REFERRAL_{self.id}"
        
        logger.debug(f"[WALLET_CREDIT] Checking for duplicate transaction: {ref}")
        if PaymentTransaction.objects.filter(reference=ref).exists():
            logger.warning(f"[WALLET_CREDIT] Duplicate detected! Skipping credit for: {ref}")
            return

        try:
            wallet, created = Wallet.objects.select_for_update().get_or_create(user=self.referrer)
            if created:
                logger.info(f"[WALLET_CREDIT] Created new wallet for user: {self.referrer.username}")
            
            balance_before = wallet.balance
            balance_after = balance_before + Decimal(self.amount)

            logger.info(
                f"[WALLET_CREDIT] Crediting {self.referrer.username}: "
                f"₦{balance_before} → ₦{balance_after} (+₦{self.amount})"
            )

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
            
            logger.info(
                f"[WALLET_CREDIT] ✅ Successfully credited {self.referrer.username} - "
                f"Transaction ID: {tx.id}"
            )
            
        except Exception as e:
            logger.error(
                f"[WALLET_CREDIT] ❌ Failed to credit wallet for earning {self.id}: {str(e)}",
                exc_info=True
            )
            raise


class CommissionTier(models.Model):
    """Defines commission rates per referral level and earning type."""
    level = models.PositiveSmallIntegerField()
    rate = models.DecimalField(max_digits=5, decimal_places=2)
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

