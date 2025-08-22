from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.conf import settings
import uuid
import secrets
import string


# ---------- CONSTANTS ----------
EMAIL_TOKEN_EXPIRY_HOURS = 24
PHONE_TOKEN_EXPIRY_MINUTES = 10


# ---------- USER MANAGER ----------
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """Create and save a User with the given email and password"""
        if not email:
            raise ValueError('The Email field must be set')

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a SuperUser"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.ADMIN)

        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


# ---------- USER MODEL ----------
class User(AbstractBaseUser, PermissionsMixin):
    MEMBER = 'member'
    ADVERTISER = 'advertiser'
    ADMIN = 'admin'

    ROLE_CHOICES = [
        (MEMBER, 'Member'),
        (ADVERTISER, 'Advertiser'),
        (ADMIN, 'Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True, blank=True, null=True)

    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone = models.CharField(
        validators=[phone_regex],
        max_length=17,
        blank=True,
        null=True,
        unique=True,
        db_index=True
    )

    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=MEMBER)

    referral_code = models.CharField(max_length=10, unique=True, blank=True, db_index=True)
    referred_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='referrals'
    )

    # Status & verification
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    # Timestamps
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Profile info
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    birth_date = models.DateField(null=True, blank=True)

    # Location
    country = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Preferences
    receive_email_notifications = models.BooleanField(default=True)
    receive_sms_notifications = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['referral_code']),
            models.Index(fields=['role']),
        ]

    def save(self, *args, **kwargs):
        # Generate unique username if missing
        if not self.username:
            base_username = self.email.split('@')[0]
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exclude(pk=self.pk).exists():
                username = f"{base_username}{counter}"
                counter += 1
            self.username = username

        # Auto-generate referral code
        if not self.referral_code:
            self.referral_code = self.generate_referral_code()

        super().save(*args, **kwargs)

    def generate_referral_code(self):
        """Generate unique referral code (8 alphanumeric chars)"""
        chars = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(chars) for _ in range(8))
            if not User.objects.filter(referral_code=code).exists():
                return code

    # ----- Display helpers -----
    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]

    def get_display_name(self):
        return self.get_full_name() or self.username or self.email

    # ----- Referrals -----
    @property
    def referral_url(self):
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        return f"{base_url}/users/ref/{self.referral_code}/"

    @property
    def total_referrals(self):
        return self.referrals.count()

    @property
    def active_referrals(self):
        return self.referrals.filter(is_active=True).count()

    # ----- Permissions -----
    def can_post_tasks(self):
        return self.role in [self.ADVERTISER, self.ADMIN] and self.is_active

    def can_moderate(self):
        return self.role == self.ADMIN and self.is_active

    def __str__(self):
        return self.get_display_name()


# ---------- USER PROFILE ----------
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Add these
    location = models.CharField(max_length=255, blank=True)

    # Already existing
    occupation = models.CharField(max_length=100, blank=True)
    company = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    skills = models.TextField(blank=True)
    experience_years = models.PositiveIntegerField(null=True, blank=True)
    tasks_completed = models.PositiveIntegerField(default=0)
    tasks_posted = models.PositiveIntegerField(default=0)
    success_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_display_name()}'s Profile"
    
    # Add this method to your UserProfile model
    @property
    def skills_list(self):
        """Return skills as a list, splitting by comma"""
        if self.skills:
            return [skill.strip() for skill in self.skills.split(',') if skill.strip()]
        return []


# ---------- VERIFICATION TOKENS ----------
class EmailVerificationToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(hours=EMAIL_TOKEN_EXPIRY_HOURS)
        super().save(*args, **kwargs)


class PhoneVerificationToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at

    def save(self, *args, **kwargs):
        if not self.token:
            # Always 6 digits
            self.token = f"{secrets.randbelow(900000) + 100000:06d}"
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=PHONE_TOKEN_EXPIRY_MINUTES)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [models.Index(fields=['user', 'token'])]
