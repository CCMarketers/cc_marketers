# tests/test_base.py
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core import mail
from unittest.mock import patch
from PIL import Image
import io

from users.models import EmailVerificationToken, PhoneVerificationToken
from referrals.models import ReferralCode, Referral
from tasks.models import Task, Submission

User = get_user_model()


class BaseTestCase(TestCase):
    """Base test case with common setup and utilities"""
    
    def setUp(self):
        """Common setup for all test cases"""
        self.client = Client()
        self.user_data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'phone': '+1234567890',
        }
        
        # Clear any existing test data
        User.objects.filter(email__contains='test').delete()
        mail.outbox = []

    def create_user(self, **kwargs):
        """Create a test user with default values"""
        defaults = {
            'email': 'user@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password': 'testpass123',
            'is_active': True,
            'email_verified': False,
            'phone_verified': False,
        }
        defaults.update(kwargs)
        
        password = defaults.pop('password')
        user = User.objects.create(**defaults)
        user.set_password(password)
        user.save()
        return user

    def create_admin_user(self, **kwargs):
        """Create an admin user"""
        defaults = {
            'role': User.ADMIN,
            'is_staff': True,
            'is_superuser': True,
        }
        defaults.update(kwargs)
        return self.create_user(**defaults)

    def create_advertiser_user(self, **kwargs):
        """Create an advertiser user"""
        defaults = {
            'role': User.ADVERTISER,
        }
        defaults.update(kwargs)
        return self.create_user(**defaults)

    def create_member_user(self, **kwargs):
        """Create a member user"""
        defaults = {
            'role': User.MEMBER,
        }
        defaults.update(kwargs)
        return self.create_user(**defaults)

    def create_referral_code(self, user=None, **kwargs):
        """Create a referral code"""
        if user is None:
            user = self.create_user()
        
        defaults = {
            'user': user,
            'is_active': True,
        }
        defaults.update(kwargs)
        return ReferralCode.objects.create(**defaults)

    def create_referral(self, referrer=None, referred=None, **kwargs):
        """Create a referral relationship"""
        if referrer is None:
            referrer = self.create_user(email='referrer@example.com')
        if referred is None:
            referred = self.create_user(email='referred@example.com')
            
        referral_code = self.create_referral_code(user=referrer)
        
        defaults = {
            'referrer': referrer,
            'referred': referred,
            'referral_code': referral_code,
            'level': 1,
        }
        defaults.update(kwargs)
        return Referral.objects.create(**defaults)

    def create_task(self, advertiser=None, **kwargs):
        """Create a test task"""
        if advertiser is None:
            advertiser = self.create_advertiser_user(email='advertiser@example.com')
            
        defaults = {
            'advertiser': advertiser,
            'title': 'Test Task',
            'description': 'Test Description',
            'reward': 100.00,
            'status': 'active',
        }
        defaults.update(kwargs)
        return Task.objects.create(**defaults)

    def create_submission(self, task=None, member=None, **kwargs):
        """Create a test submission"""
        if task is None:
            task = self.create_task()
        if member is None:
            member = self.create_member_user(email='member@example.com')
            
        defaults = {
            'task': task,
            'member': member,
            'status': 'pending',
            'content': 'Test submission content',
        }
        defaults.update(kwargs)
        return Submission.objects.create(**defaults)

    def create_email_verification_token(self, user=None, **kwargs):
        """Create an email verification token"""
        if user is None:
            user = self.create_user()
            
        defaults = {
            'user': user,
        }
        defaults.update(kwargs)
        return EmailVerificationToken.objects.create(**defaults)

    def create_phone_verification_token(self, user=None, **kwargs):
        """Create a phone verification token"""
        if user is None:
            user = self.create_user()
            
        defaults = {
            'user': user,
        }
        defaults.update(kwargs)
        return PhoneVerificationToken.objects.create(**defaults)

    def create_temp_image(self):
        """Create a temporary image file for testing"""
        image = Image.new('RGB', (100, 100), color='red')
        temp_file = io.BytesIO()
        image.save(temp_file, format='JPEG')
        temp_file.name = 'test.jpg'
        temp_file.seek(0)
        return temp_file

    def login_user(self, user=None):
        """Login a user"""
        if user is None:
            user = self.create_user()
        self.client.force_login(user)
        return user

    def assertRedirectsToLogin(self, response, next_url=None):
        """Assert response redirects to login page"""
        expected_url = reverse('users:login')
        if next_url:
            expected_url += f'?next={next_url}'
        self.assertRedirects(response, expected_url)

    def assertFormError(self, response, form_name, field, error_message):
        """Assert form has specific error"""
        form = response.context.get(form_name)
        self.assertIsNotNone(form, f"Form '{form_name}' not found in context")
        
        if field:
            field_errors = form.errors.get(field, [])
            self.assertIn(error_message, field_errors, 
                         f"Error '{error_message}' not found in field '{field}' errors: {field_errors}")
        else:
            # Non-field errors
            non_field_errors = form.non_field_errors()
            self.assertIn(error_message, non_field_errors,
                         f"Error '{error_message}' not found in non-field errors: {non_field_errors}")

    def assertEmailSent(self, count=1, to_email=None, subject_contains=None):
        """Assert email was sent"""
        self.assertEqual(len(mail.outbox), count, f"Expected {count} emails, got {len(mail.outbox)}")
        
        if count > 0:
            email = mail.outbox[-1]  # Get latest email
            if to_email:
                self.assertIn(to_email, email.to)
            if subject_contains:
                self.assertIn(subject_contains, email.subject)

    def assertNoEmailSent(self):
        """Assert no email was sent"""
        self.assertEmailSent(count=0)

    def assertMessageExists(self, response, level=None, message_contains=None):
        """Assert message exists in response"""
        messages = list(response.context.get('messages', []))
        
        if level:
            level_messages = [m for m in messages if m.level == level]
            self.assertTrue(level_messages, f"No messages with level {level} found")
            messages = level_messages
            
        if message_contains:
            message_texts = [str(m) for m in messages]
            found = any(message_contains in text for text in message_texts)
            self.assertTrue(found, f"Message containing '{message_contains}' not found in: {message_texts}")


class MockTestCase(BaseTestCase):
    """Base test case with common mocks"""
    
    def setUp(self):
        super().setUp()
        
        # Mock external services
        self.sms_patcher = patch('users.views.send_sms')
        self.mock_sms = self.sms_patcher.start()
        self.mock_sms.return_value = True
        
        self.email_patcher = patch('core.services.send_verification_email')
        self.mock_email = self.email_patcher.start()
        self.mock_email.return_value = True

    def tearDown(self):
        super().tearDown()
        self.sms_patcher.stop()
        self.email_patcher.stop()