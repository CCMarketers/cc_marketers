# subscriptions/models.py
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone


class ActiveSubscriptionManager(models.Manager):
    """Custom manager to get only active & non-expired subscriptions."""
    def get_queryset(self):
        return super().get_queryset().filter(
            status="active",
            expiry_date__gt=timezone.now()
        )


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(default=30)  # e.g. 30 for monthly, 365 for yearly
    business_volume = models.PositiveIntegerField(default=0)
    referral_commission = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )
    commission_to_tree = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00")
    )
    daily_ad_limit = models.PositiveIntegerField(default=0)  # 0 means unlimited
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - ${self.price}"

    class Meta:
        ordering = ["price", "created_at"]


class UserSubscription(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    start_date = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE
    )
    auto_renewal = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Custom managers
    objects = models.Manager()
    active = ActiveSubscriptionManager()

    def save(self, *args, **kwargs):
        """
        Automatically calculate expiry_date on creation
        if not provided.
        """
        if not self.pk and not self.expiry_date:
            self.expiry_date = timezone.now() + timezone.timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)

    @property
    def is_active(self) -> bool:
        """True if subscription is active & not expired."""
        return (
            self.status == self.STATUS_ACTIVE
            and self.expiry_date > timezone.now()
        )

    @property
    def days_remaining(self) -> int:
        """Number of days left until expiry."""
        remaining = self.expiry_date - timezone.now()
        return max(0, remaining.days)

    def __str__(self):
        # fall back gracefully if get_display_name does not exist
        username = getattr(self.user, "get_display_name", lambda: str(self.user))()
        return f"{username} - {self.plan.name} ({self.status})"

    class Meta:
        ordering = ["-created_at"]
