# tasks/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid
from django.db.models.expressions import Combinable


class Task(models.Model):
    TASK_STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    advertiser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='posted_tasks'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    payout_per_slot = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    total_slots = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    remaining_slots = models.PositiveIntegerField()
    deadline = models.DateTimeField()
    proof_instructions = models.TextField()
    status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'deadline']),
        ]

    def save(self, *args, **kwargs):
        """Auto initialise and adjust remaining_slots."""
        if not self.pk:  # new task
            self.remaining_slots = self.total_slots
        else:
            # only clamp if remaining_slots is a real int, not an F() expression
            if not isinstance(self.remaining_slots, Combinable):
                if self.remaining_slots > self.total_slots:
                    self.remaining_slots = self.total_slots
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Task #{self.pk}: {self.title}"

    @property
    def is_full(self):
        return self.remaining_slots <= 0

    @property
    def is_expired(self):
        return timezone.now() > self.deadline

    @property
    def total_payout(self):
        return self.payout_per_slot * self.total_slots

    @property
    def filled_slots(self):
        return self.total_slots - self.remaining_slots


class Submission(models.Model):
    SUBMISSION_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('resubmitted', 'Resubmitted'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='submissions')
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_submissions'
    )
    proof_text = models.TextField(blank=True)
    proof_file = models.FileField(upload_to='task_proofs/', blank=True, null=True)
    screenshot = models.ImageField(upload_to='task_screenshots/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=SUBMISSION_STATUS_CHOICES, default='pending')
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_submissions'
    )

    class Meta:
        ordering = ['-submitted_at']
        constraints = [
            models.UniqueConstraint(fields=['task', 'member'], name='unique_submission_per_member'),
        ]
        indexes = [
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Submission #{self.pk} by {self.member} for {self.task.title}"

    @property
    def member_name(self):
        return getattr(self.member, 'get_display_name', lambda: self.member.username)()

    def mark_reviewed(self, reviewer):
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()

    def approve(self, reviewer):
        self.mark_reviewed(reviewer)
        self.status = 'approved'
        self.save()

    def reject(self, reviewer, reason):
        self.mark_reviewed(reviewer)
        self.status = 'rejected'
        self.rejection_reason = reason
        self.save()


class Dispute(models.Model):
    DISPUTE_STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Under Investigation'),
        ('resolved_favor_member', 'Resolved - Favor Member'),
        ('resolved_favor_advertiser', 'Resolved - Favor Advertiser'),
        ('closed', 'Closed'),
    ]

    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, related_name='dispute')
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='raised_disputes'
    )
    reason = models.TextField()
    admin_notes = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=DISPUTE_STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_disputes'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Dispute #{self.pk} - {self.submission.task.title}"


class TaskWallet(models.Model):
    """Wallet for posting tasks (business members only)."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Task Wallet - {self.user.username}: ${self.balance}"

    def get_available_balance(self):
        return self.balance


class TaskWalletTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]
    CATEGORIES = [
        ('subscription_bonus', 'Subscription Bonus'),
        ('task_posting', 'Task Posting'),
        ('topup_from_main', 'Top-up from Main Wallet'),
        ('admin_adjustment', 'Admin Adjustment'),
    ]
    STATUS = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    category = models.CharField(max_length=30, choices=CATEGORIES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS, default='success')
    description = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.transaction_type} ${self.amount} ({self.category})"
