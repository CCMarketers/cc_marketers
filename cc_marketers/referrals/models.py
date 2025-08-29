# referrals/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
import string
import random

from wallets.models import Wallet, Transaction
from decimal import Decimal


class ReferralCode(models.Model):
    """Unique referral code assigned to each user"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_code'
    )
    code = models.CharField(max_length=10, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)

    def generate_code(self):
        """Generate a unique referral code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not ReferralCode.objects.filter(code=code).exists():
                return code

    def __str__(self):
        return f"{self.user} - {self.code}"


class Referral(models.Model):
    """Tracks referrals and their relationship levels"""
    LEVEL_CHOICES = [
        (1, 'Direct (Level 1)'),
        (2, 'Indirect (Level 2)'),
        (3, 'Level 3'),
    ]

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referrals_made'
    )
    referred = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_source'
    )
    level = models.IntegerField(choices=LEVEL_CHOICES, default=1)
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['referrer', 'referred']

    def __str__(self):
        return f"{self.referrer} → {self.referred} (Level {self.level})"

class ReferralEarning(models.Model):
    """Tracks earnings generated from referrals"""
    EARNING_TYPES = [
        ('signup', 'New Signup'),
        ('task_completion', 'Task Completion'),
        ('advertiser_funding', 'Advertiser Funding'),
        ('subscription', 'Subscription Purchase'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_earnings'
    )
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='earnings_generated'
    )
    referral = models.ForeignKey("Referral", on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    earning_type = models.CharField(max_length=20, choices=EARNING_TYPES)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)  # Percentage
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='approved')  # 👈 Default now approved
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        new = self.pk is None
        # Auto-set approved timestamp if instant credit
        if new and self.status == 'approved':
            self.approved_at = timezone.now()

        super().save(*args, **kwargs)

        # Auto-credit on creation
        if new and self.status == 'approved':
            self.credit_wallet()

    def approve(self):
        """Kept for compatibility — instantly approve and credit"""
        self.status = 'approved'
        self.approved_at = timezone.now()
        self.save()

    def credit_wallet(self):
        """Credit referral bonus into wallet"""
        # Prevent duplicate crediting
        if Transaction.objects.filter(reference=f"REFERRAL_{self.id}").exists():
            return

        wallet, _ = Wallet.objects.get_or_create(user=self.referrer)
        balance_before = wallet.balance
        balance_after = balance_before + Decimal(self.amount)

        tx = Transaction.objects.create(
            user=self.referrer,
            transaction_type='credit',
            category='referral_bonus',
            amount=self.amount,
            balance_before=balance_before,
            balance_after=balance_after,
            status='success',
            reference=f"REFERRAL_{self.id}",
            description=f"Referral earning from {self.referred_user.username}"
        )

        # Save transaction reference
        self.transaction_id = str(tx.id)
        super().save(update_fields=['transaction_id'])

        # Update wallet balance
        wallet.balance = balance_after
        wallet.save(update_fields=['balance'])

class CommissionTier(models.Model):
    """Defines commission rates per referral level and earning type"""
    level = models.IntegerField()
    rate = models.DecimalField(max_digits=5, decimal_places=2)  # Percentage
    earning_type = models.CharField(max_length=20, choices=ReferralEarning.EARNING_TYPES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['level', 'earning_type']

    def __str__(self):
        return f"Level {self.level} - {self.rate}% for {self.earning_type}"
