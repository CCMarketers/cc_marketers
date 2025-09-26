from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

import uuid
import secrets
from decimal import Decimal


# ---------- CONSTANTS ----------
EMAIL_TOKEN_EXPIRY_HOURS = 24
PHONE_TOKEN_EXPIRY_MINUTES = 10


# ---------- USER MANAGER ----------
class UserManager(BaseUserManager):
    """Custom user manager that normalizes email and optionally sets a username.

    Use `create_user` and `create_superuser` as the canonical constructors.
    """

    def _create_user(self, email: str, password: str | None = None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        # don't set username automatically here; let model handle generation
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.ADMIN)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


# ---------- USER MODEL ----------
class User(AbstractBaseUser, PermissionsMixin):
    """Primary user model.

    - Uses UUID primary key for safer sharing and horizontal scaling.
    - Email is the unique identifier (USERNAME_FIELD).
    - Some convenience helpers and lightweight properties.
    """

    MEMBER = "member"
    ADVERTISER = "advertiser"
    ADMIN = "admin"

    ROLE_CHOICES = [
        (MEMBER, "Member"),
        (ADVERTISER, "Advertiser"),
    ]

    CURRENCY_CHOICES = [
        ('NGN', 'Nigerian Naira'),
        ('GHS', 'Ghanaian Cedi'),
        ('KES', 'Kenyan Shilling'),
        ('USD', 'US Dollar'),
    ]
    
    COUNTRY_CHOICES = [
        ('NG', 'Nigeria'),
        ('GH', 'Ghana'),
        ('KE', 'Kenya'),
        ('US', 'United States'),
    ]
    
    preferred_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='NGN'
    )
    country = models.CharField(
        max_length=2,
        choices=COUNTRY_CHOICES,
        null=True,
        blank=True
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(_("email address"), unique=True, db_index=True)
    username = models.CharField(
        max_length=150, unique=True, blank=True, null=True, help_text=_("Optional display username")
    )

    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{9,15}$",
        message=_("Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."),
    )
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
    )

    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=MEMBER, db_index=True)

    # Status & verification
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False, db_index=True)
    phone_verified = models.BooleanField(default=False)

    # Timestamps
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Profile info
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    birth_date = models.DateField(null=True, blank=True)

    # Location
    state = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Preferences
    receive_email_notifications = models.BooleanField(default=True)
    receive_sms_notifications = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["role"]),
            models.Index(fields=["email_verified"]),
        ]

    def save(self, *args, **kwargs):
        # Ensure admin role always has staff access
        if self.role == self.ADMIN:
            self.is_staff = True

        # Generate unique username if missing (best-effort; avoids race conditions but not guaranteed)
        if not self.username:
            base_username = (self.email.split("@")[0] if self.email else "user").lower()
            username = base_username
            counter = 1
            # Use filter with exclude(pk=self.pk) to allow updating existing users
            while User.objects.filter(username=username).exclude(pk=self.pk).exists():
                username = f"{base_username}{counter}"
                counter += 1
            self.username = username

        super().save(*args, **kwargs)

    # ----- Display helpers -----
    def get_full_name(self) -> str:
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else ""

    def get_short_name(self) -> str:
        return self.first_name or (self.email.split("@")[0] if self.email else "")

    def get_display_name(self) -> str:
        return self.get_full_name() or self.username or (self.email or "")

    def __str__(self) -> str:
        return self.get_display_name()

    # ----- Permissions helpers -----
    def can_post_tasks(self) -> bool:
        return self.role in [self.ADVERTISER, self.ADMIN] and self.is_active

    def can_moderate(self) -> bool:
        return self.role == self.ADMIN and self.is_active

    # ----- Lightweight subscription conveniences (non-blocking lookups) -----
    @property
    def active_subscription(self):
        # Avoid importing subscription model here to reduce coupling; assume related_name 'subscriptions'
        try:
            return self.subscriptions.filter(status="active", expiry_date__gt=timezone.now()).order_by("-expiry_date").first()
        except Exception:
            return None

    @property
    def is_subscribed(self) -> bool:
        return self.active_subscription is not None

    @property
    def subscription_plan(self):
        sub = self.active_subscription
        return getattr(sub, "plan", None) if sub else None


# ---------- USER PROFILE ----------
class UserProfile(models.Model):
    """Extended profile for users kept in a separate table to allow lightweight user lookups."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")

    location = models.CharField(max_length=255, blank=True)

    occupation = models.CharField(max_length=100, blank=True)
    company = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    skills = models.TextField(blank=True, help_text=_("Comma-separated skills"))
    experience_years = models.PositiveIntegerField(null=True, blank=True)
    success_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.00"))
    total_reviews = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profiles"
        indexes = [models.Index(fields=["user"])]

    def __str__(self) -> str:
        return f"{self.user.get_display_name()}\'s Profile"

    @property
    def skills_list(self) -> list:
        """Return skills as a list, splitting by comma."""
        if self.skills:
            return [s.strip() for s in self.skills.split(",") if s.strip()]
        return []

    @property
    def tasks_posted(self) -> int:
        """Number of tasks this user has posted as advertiser (related_name expected 'posted_tasks')."""
        try:
            return self.user.posted_tasks.count()
        except Exception:
            return 0

    @property
    def tasks_completed(self) -> int:
        """Number of approved submissions this user has completed (related_name expected 'task_submissions')."""
        try:
            return self.user.task_submissions.filter(status="approved").count()
        except Exception:
            return 0


# ---------- VERIFICATION TOKENS ----------
class EmailVerificationToken(models.Model):
    """Time-limited token for email verification.

    Tokens are seeded using Python's `secrets` module and stored hashed if desired later.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_tokens")
    token = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "email_verification_tokens"
        indexes = [models.Index(fields=["user", "token"])]

    def __str__(self) -> str:
        return f"EmailVerificationToken(user_id={self.user_id}, used={self.used})"

    def is_valid(self) -> bool:
        return not self.used and timezone.now() < self.expires_at

    def save(self, *args, **kwargs):
        if not self.token:
            # Use token_urlsafe which is safe for URLs and reasonably long
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(hours=EMAIL_TOKEN_EXPIRY_HOURS)
        super().save(*args, **kwargs)


class PhoneVerificationToken(models.Model):
    """Short numeric token for phone verification."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="phone_tokens")
    token = models.CharField(max_length=6, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "phone_verification_tokens"
        indexes = [models.Index(fields=["user", "token"])]

    def __str__(self) -> str:
        return f"PhoneVerificationToken(user_id={self.user_id}, token={self.token})"

    def is_valid(self) -> bool:
        return not self.used and timezone.now() < self.expires_at

    def save(self, *args, **kwargs):
        if not self.token:
            # Generate a zero-padded 6-digit number
            self.token = f"{secrets.randbelow(900000) + 100000:06d}"
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=PHONE_TOKEN_EXPIRY_MINUTES)
        super().save(*args, **kwargs)
