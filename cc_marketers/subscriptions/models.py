# subscriptions/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal



class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField(default=30)  # e.g. 30 for monthly, 365 for yearly
    business_volume = models.IntegerField(default=0)
    referral_commission = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    commission_to_tree = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    daily_ad_limit = models.IntegerField(default=0)  # 0 means unlimited
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ${self.price}"

    class Meta:
        ordering = ['price', 'created_at']



class UserSubscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    # ✅ use AUTH_USER_MODEL instead of django’s default User
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions'
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    start_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    auto_renewal = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.expiry_date:
            self.expiry_date = timezone.now() + timezone.timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        return self.status == 'active' and self.expiry_date > timezone.now()

    @property
    def days_remaining(self):
        if self.expiry_date > timezone.now():
            return (self.expiry_date - timezone.now()).days
        return 0

    def __str__(self):
        return f"{self.user.get_display_name()} - {self.plan.name} ({self.status})"

    class Meta:
        ordering = ['-created_at']

