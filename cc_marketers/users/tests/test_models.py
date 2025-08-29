# tests/test_models.py
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, Mock

from django.test import TestCase
# from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.utils import IntegrityError

from users.models import (
    User, UserProfile, EmailVerificationToken, PhoneVerificationToken,
    EMAIL_TOKEN_EXPIRY_HOURS, PHONE_TOKEN_EXPIRY_MINUTES
)

# User = get_user_model()


class UserManagerTest(TestCase):
    """Test UserManager methods"""

    def test_create_user_success(self):
        """Test successful user creation"""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertTrue(user.check_password('testpass123'))
        self.assertEqual(user.role, User.MEMBER)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_create_user_without_email_raises_error(self):
        """Test user creation without email raises ValueError"""
        with self.assertRaises(ValueError) as cm:
            User.objects.create_user(email='', password='testpass123')
        self.assertEqual(str(cm.exception), 'The Email field must be set')

    def test_create_user_without_password(self):
        """Test user creation without password sets unusable password"""
        user = User.objects.create_user(email='test@example.com')
        self.assertFalse(user.has_usable_password())

    def test_create_user_normalizes_email(self):
        """Test email normalization"""
        user = User.objects.create_user(
            email='Test@EXAMPLE.COM',
            password='testpass123'
        )
        self.assertEqual(user.email, 'Test@example.com')

    def test_create_superuser_success(self):
        """Test successful superuser creation"""
        superuser = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        self.assertEqual(superuser.email, 'admin@example.com')
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertEqual(superuser.role, User.ADMIN)

    def test_create_superuser_missing_is_staff_raises_error(self):
        """Test superuser creation with is_staff=False raises ValueError"""
        with self.assertRaises(ValueError) as cm:
            User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass123',
                is_staff=False
            )
        self.assertEqual(str(cm.exception), 'Superuser must have is_staff=True.')

    def test_create_superuser_missing_is_superuser_raises_error(self):
        """Test superuser creation with is_superuser=False raises ValueError"""
        with self.assertRaises(ValueError) as cm:
            User.objects.create_superuser(
                email='admin@example.com',
                password='adminpass123',
                is_superuser=False
            )
        self.assertEqual(str(cm.exception), 'Superuser must have is_superuser=True.')


class UserModelTest(TestCase):
    """Test User model functionality"""

    def setUp(self):
        self.user_data = {
            'email': 'test@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'phone': '+1234567890',
            'password': 'testpass123'
        }

    def test_user_creation_with_valid_data(self):
        """Test user creation with valid data"""
        user = User.objects.create_user(**self.user_data)
        self.assertIsInstance(user.id, uuid.UUID)
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertEqual(user.phone, '+1234567890')
        self.assertEqual(user.role, User.MEMBER)
        self.assertTrue(user.is_active)
        self.assertFalse(user.email_verified)
        self.assertFalse(user.phone_verified)

    def test_unique_email_constraint(self):
        """Test email uniqueness constraint"""
        User.objects.create_user(**self.user_data)
        with self.assertRaises(IntegrityError):
            User.objects.create_user(email='test@example.com', password='pass123')

    def test_unique_phone_constraint(self):
        """Test phone uniqueness constraint"""
        User.objects.create_user(**self.user_data)
        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                email='another@example.com',
                phone='+1234567890',
                password='pass123'
            )

    def test_username_auto_generation(self):
        """Test automatic username generation from email"""
        user = User.objects.create_user(email='john.doe@example.com', password='pass123')
        self.assertEqual(user.username, 'john.doe')

    def test_username_collision_handling(self):
        """Test handling of username collisions"""
        # Create first user
        user1 = User.objects.create_user(email='john@example.com', password='pass123')
        self.assertEqual(user1.username, 'john')
        
        # Create second user with same base username
        user2 = User.objects.create_user(email='john@another.com', password='pass123')
        self.assertEqual(user2.username, 'john1')
        
        # Create third user
        user3 = User.objects.create_user(email='john@third.com', password='pass123')
        self.assertEqual(user3.username, 'john2')

    def test_admin_role_sets_staff_status(self):
        """Test admin role automatically sets is_staff=True"""
        user = User.objects.create_user(
            email='admin@example.com',
            password='pass123',
            role=User.ADMIN
        )
        self.assertTrue(user.is_staff)

    def test_phone_validation(self):
        """Test phone number validation"""
        # Valid phone numbers
        valid_phones = ['+1234567890', '+12345678901234', '1234567890']
        for phone in valid_phones:
            user = User(email=f'test{phone[-4:]}@example.com', phone=phone)
            try:
                user.full_clean()
            except ValidationError:
                self.fail(f"Phone {phone} should be valid")

        # Invalid phone numbers
        invalid_phones = ['123', '+123456789012345678', 'abc123', '']
        for phone in invalid_phones:
            user = User(email=f'test{len(phone)}@example.com', phone=phone)
            if phone:  # Skip empty string as it's allowed
                with self.assertRaises(ValidationError):
                    user.full_clean()

    def test_get_full_name(self):
        """Test get_full_name method"""
        user = User(email='test@example.com', first_name='John', last_name='Doe')
        self.assertEqual(user.get_full_name(), 'John Doe')
        
        user.first_name = 'John'
        user.last_name = ''
        self.assertEqual(user.get_full_name(), 'John')
        
        user.first_name = ''
        user.last_name = 'Doe'
        self.assertEqual(user.get_full_name(), 'Doe')
        
        user.first_name = ''
        user.last_name = ''
        self.assertEqual(user.get_full_name(), 'test@example.com')

    def test_get_short_name(self):
        """Test get_short_name method"""
        user = User(email='test@example.com', first_name='John')
        self.assertEqual(user.get_short_name(), 'John')
        
        user.first_name = ''
        self.assertEqual(user.get_short_name(), 'test')

    def test_get_display_name(self):
        """Test get_display_name method"""
        user = User(email='test@example.com', first_name='John', last_name='Doe')
        user.username = 'johndoe'
        
        # With full name
        self.assertEqual(user.get_display_name(), 'John Doe')
        
        # Without names, with username
        user.first_name = ''
        user.last_name = ''
        self.assertEqual(user.get_display_name(), 'johndoe')
        
        # Without names and username
        user.username = ''
        self.assertEqual(user.get_display_name(), 'test@example.com')

    def test_can_post_tasks(self):
        """Test can_post_tasks permission method"""
        # Member cannot post tasks
        member = User(role=User.MEMBER, is_active=True)
        self.assertFalse(member.can_post_tasks())
        
        # Advertiser can post tasks
        advertiser = User(role=User.ADVERTISER, is_active=True)
        self.assertTrue(advertiser.can_post_tasks())
        
        # Admin can post tasks
        admin = User(role=User.ADMIN, is_active=True)
        self.assertTrue(admin.can_post_tasks())
        
        # Inactive advertiser cannot post tasks
        inactive_advertiser = User(role=User.ADVERTISER, is_active=False)
        self.assertFalse(inactive_advertiser.can_post_tasks())

    def test_can_moderate(self):
        """Test can_moderate permission method"""
        # Only active admin can moderate
        admin = User(role=User.ADMIN, is_active=True)
        self.assertTrue(admin.can_moderate())
        
        # Inactive admin cannot moderate
        inactive_admin = User(role=User.ADMIN, is_active=False)
        self.assertFalse(inactive_admin.can_moderate())
        
        # Non-admin cannot moderate
        advertiser = User(role=User.ADVERTISER, is_active=True)
        self.assertFalse(advertiser.can_moderate())

    def test_str_representation(self):
        """Test string representation"""
        user = User(email='test@example.com', first_name='John', last_name='Doe')
        self.assertEqual(str(user), 'John Doe')

    def test_role_choices(self):
        """Test role choices are properly defined"""
        self.assertEqual(User.MEMBER, 'member')
        self.assertEqual(User.ADVERTISER, 'advertiser')
        self.assertEqual(User.ADMIN, 'admin')
        
        expected_choices = [
            ('member', 'Member'),
            ('advertiser', 'Advertiser'),
            ('admin', 'Admin'),
        ]
        self.assertEqual(User.ROLE_CHOICES, expected_choices)


class UserProfileModelTest(TestCase):
    """Test UserProfile model functionality"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_user_profile_creation(self):
        """Test UserProfile creation"""
        profile = self.user.profile
        profile.occupation = 'Developer'
        profile.company = 'Tech Corp'
        profile.skills = 'Python, Django'
        profile.experience_years = 5
        profile.save()

        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.occupation, 'Developer')
        self.assertEqual(profile.company, 'Tech Corp')
        self.assertEqual(profile.skills, 'Python, Django')
        self.assertEqual(profile.experience_years, 5)
        self.assertEqual(profile.success_rate, Decimal('0.00'))
        self.assertEqual(profile.average_rating, Decimal('0.00'))
        self.assertEqual(profile.total_reviews, 0)

    def test_skills_list_property(self):
        """Test skills_list property"""
        profile = self.user.profile
        
        # Empty skills
        self.assertEqual(profile.skills_list, [])
        
        # Single skill
        profile.skills = 'Python'
        self.assertEqual(profile.skills_list, ['Python'])
        
        # Multiple skills
        profile.skills = 'Python, Django, JavaScript'
        self.assertEqual(profile.skills_list, ['Python', 'Django', 'JavaScript'])
        
        # Skills with extra whitespace
        profile.skills = ' Python , Django , JavaScript '
        self.assertEqual(profile.skills_list, ['Python', 'Django', 'JavaScript'])
        
        # Empty skills in list
        profile.skills = 'Python, , Django'
        self.assertEqual(profile.skills_list, ['Python', 'Django'])

    @patch('users.models.UserProfile.user')
    def test_tasks_posted_property(self, mock_user):
        """Test tasks_posted property"""
        mock_posted_tasks = Mock()
        mock_posted_tasks.count.return_value = 5
        mock_user.posted_tasks = mock_posted_tasks
        
        profile = UserProfile(user=mock_user)
        self.assertEqual(profile.tasks_posted, 5)

    @patch('users.models.UserProfile.user')
    def test_tasks_completed_property(self, mock_user):
        """Test tasks_completed property"""
        mock_submissions = Mock()
        mock_filter = Mock()
        mock_filter.count.return_value = 3
        mock_submissions.filter.return_value = mock_filter
        mock_user.task_submissions = mock_submissions
        
        profile = UserProfile(user=mock_user)
        result = profile.tasks_completed
        
        mock_submissions.filter.assert_called_once_with(status="approved")
        self.assertEqual(result, 3)

    def test_str_representation(self):
        """Test string representation"""
        profile = self.user.profile
        expected = f"{self.user.get_display_name()}'s Profile"
        self.assertEqual(str(profile), expected)

    def test_one_to_one_relationship(self):
        """Test one-to-one relationship with User"""
        profile = self.user.profile
        
        # Access profile from user
        self.assertEqual(self.user.profile, profile)
        
        # Cannot create another profile for same user
        with self.assertRaises(IntegrityError):
            UserProfile.objects.create(user=self.user)


class EmailVerificationTokenTest(TestCase):
    """Test EmailVerificationToken model"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_token_creation(self):
        """Test token creation with auto-generated values"""
        token = EmailVerificationToken.objects.create(user=self.user)
        
        self.assertEqual(token.user, self.user)
        self.assertIsNotNone(token.token)
        self.assertFalse(token.used)
        self.assertIsNotNone(token.expires_at)
        
        # Check expiry time is approximately correct
        expected_expiry = timezone.now() + timedelta(hours=EMAIL_TOKEN_EXPIRY_HOURS)
        self.assertAlmostEqual(
            token.expires_at,
            expected_expiry,
            delta=timedelta(seconds=10)
        )

    def test_token_uniqueness(self):
        """Test token uniqueness"""
        token1 = EmailVerificationToken.objects.create(user=self.user)
        
        user2 = User.objects.create_user(email='test2@example.com', password='pass123')
        token2 = EmailVerificationToken.objects.create(user=user2)
        
        self.assertNotEqual(token1.token, token2.token)

    def test_is_valid_method_fresh_token(self):
        """Test is_valid method with fresh token"""
        token = EmailVerificationToken.objects.create(user=self.user)
        self.assertTrue(token.is_valid())

    def test_is_valid_method_used_token(self):
        """Test is_valid method with used token"""
        token = EmailVerificationToken.objects.create(user=self.user)
        token.used = True
        token.save()
        self.assertFalse(token.is_valid())

    def test_is_valid_method_expired_token(self):
        """Test is_valid method with expired token"""
        token = EmailVerificationToken.objects.create(user=self.user)
        token.expires_at = timezone.now() - timedelta(hours=1)
        token.save()
        self.assertFalse(token.is_valid())

    def test_manual_token_and_expiry(self):
        """Test creating token with manual values"""
        custom_token = 'custom_token_value'
        custom_expiry = timezone.now() + timedelta(hours=48)
        
        token = EmailVerificationToken.objects.create(
            user=self.user,
            token=custom_token,
            expires_at=custom_expiry
        )
        
        self.assertEqual(token.token, custom_token)
        self.assertEqual(token.expires_at, custom_expiry)


class PhoneVerificationTokenTest(TestCase):
    """Test PhoneVerificationToken model"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_token_creation(self):
        """Test token creation with auto-generated values"""
        token = PhoneVerificationToken.objects.create(user=self.user)
        
        self.assertEqual(token.user, self.user)
        self.assertIsNotNone(token.token)
        self.assertEqual(len(token.token), 6)
        self.assertTrue(token.token.isdigit())
        self.assertFalse(token.used)
        self.assertIsNotNone(token.expires_at)
        
        # Check expiry time is approximately correct
        expected_expiry = timezone.now() + timedelta(minutes=PHONE_TOKEN_EXPIRY_MINUTES)
        self.assertAlmostEqual(
            token.expires_at,
            expected_expiry,
            delta=timedelta(seconds=10)
        )

    def test_token_format(self):
        """Test token format is always 6 digits"""
        for _ in range(10):  # Test multiple generations
            token = PhoneVerificationToken.objects.create(user=self.user)
            self.assertEqual(len(token.token), 6)
            self.assertTrue(token.token.isdigit())
            self.assertTrue(100000 <= int(token.token) <= 999999)
            token.delete()  # Clean up for next iteration

    def test_is_valid_method_fresh_token(self):
        """Test is_valid method with fresh token"""
        token = PhoneVerificationToken.objects.create(user=self.user)
        self.assertTrue(token.is_valid())

    def test_is_valid_method_used_token(self):
        """Test is_valid method with used token"""
        token = PhoneVerificationToken.objects.create(user=self.user)
        token.used = True
        token.save()
        self.assertFalse(token.is_valid())

    def test_is_valid_method_expired_token(self):
        """Test is_valid method with expired token"""
        token = PhoneVerificationToken.objects.create(user=self.user)
        token.expires_at = timezone.now() - timedelta(minutes=1)
        token.save()
        self.assertFalse(token.is_valid())

    def test_manual_token_and_expiry(self):
        """Test creating token with manual values"""
        custom_token = '123456'
        custom_expiry = timezone.now() + timedelta(minutes=30)
        
        token = PhoneVerificationToken.objects.create(
            user=self.user,
            token=custom_token,
            expires_at=custom_expiry
        )
        
        self.assertEqual(token.token, custom_token)
        self.assertEqual(token.expires_at, custom_expiry)

    def test_token_index(self):
        """Test database index on user and token fields"""
        # This is more of a structural test - ensure the index is defined
        # The actual index creation is tested during migrations
        token = PhoneVerificationToken.objects.create(user=self.user)
        
        # Should be able to query efficiently by user and token
        found_token = PhoneVerificationToken.objects.get(
            user=self.user,
            token=token.token
        )
        self.assertEqual(found_token, token)


class UserModelDatabaseConstraintsTest(TestCase):
    """Test database constraints and indexes"""

    def test_email_index(self):
        """Test email field has database index"""
        user = User.objects.create_user(email='test@example.com', password='pass123')
        
        # Should be able to query efficiently by email
        found_user = User.objects.get(email='test@example.com')
        self.assertEqual(found_user, user)

    def test_phone_index(self):
        """Test phone field has database index"""
        user = User.objects.create_user(
            email='test@example.com',
            password='pass123',
            phone='+1234567890'
        )
        
        # Should be able to query efficiently by phone
        found_user = User.objects.get(phone='+1234567890')
        self.assertEqual(found_user, user)

    def test_role_index(self):
        """Test role field has database index"""
        user = User.objects.create_user(
            email='test@example.com',
            password='pass123',
            role=User.ADVERTISER
        )
        
        # Should be able to query efficiently by role
        advertisers = User.objects.filter(role=User.ADVERTISER)
        self.assertIn(user, advertisers)

    def test_username_uniqueness(self):
        """Test username uniqueness constraint"""
        User.objects.create_user(email='test1@example.com', password='pass123')
        
        # Manually setting the same username should fail
        user2 = User(email='test2@example.com', username='test1')
        user2.set_password('pass123')
        
        with self.assertRaises(IntegrityError):
            user2.save()