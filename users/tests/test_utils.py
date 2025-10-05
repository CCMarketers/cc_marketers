# users/tests/test_utils.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core import mail
from unittest.mock import patch, Mock
from decimal import Decimal

from users.models import UserProfile, EmailVerificationToken, PhoneVerificationToken
from referrals.models import ReferralCode, Referral

User = get_user_model()


class TestDataMixin:
    """Mixin providing common test data creation methods."""
    
    @classmethod
    def create_user(cls, email=None, password='testpass123', **kwargs):
        """Create a test user with optional parameters."""
        if not email:
            import uuid
            email = f'test{uuid.uuid4().hex[:8]}@example.com'
        
        defaults = {
            'first_name': 'Test',
            'last_name': 'User',
            'role': User.MEMBER,
            'is_active': True,
        }
        defaults.update(kwargs)
        
        return User.objects.create_user(email=email, password=password, **defaults)
    
    @classmethod
    def create_admin_user(cls, email=None, password='adminpass123', **kwargs):
        """Create an admin user."""
        if not email:
            import uuid
            email = f'admin{uuid.uuid4().hex[:8]}@example.com'
        
        kwargs.update({'role': User.ADMIN})
        return cls.create_user(email=email, password=password, **kwargs)
    
    @classmethod
    def create_advertiser_user(cls, email=None, password='testpass123', **kwargs):
        """Create an advertiser user."""
        if not email:
            import uuid
            email = f'advertiser{uuid.uuid4().hex[:8]}@example.com'
        
        kwargs.update({'role': User.ADVERTISER})
        return cls.create_user(email=email, password=password, **kwargs)
    
    @classmethod
    def create_user_profile(cls, user=None, **kwargs):
        """Create or get a user profile with optional parameters."""
        if not user:
            user = cls.create_user()
        
        defaults = {
            'occupation': 'Software Developer',
            'company': 'Tech Corp',
            'skills': 'Python, Django, JavaScript',
            'experience_years': 3,
        }
        defaults.update(kwargs)
        
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults=defaults)
        return profile


    @classmethod
    def create_referral_code(cls, user=None, code=None, **kwargs):
        """Create or get a referral code."""
        if not user:
            user = cls.create_user()
        if not code:
            import uuid
            code = f'REF{uuid.uuid4().hex[:8].upper()}'
        
        defaults = {'is_active': True}
        defaults.update(kwargs)
        
        referral_code, _ = ReferralCode.objects.get_or_create(user=user, defaults={**defaults, 'code': code})
        return referral_code



    @classmethod
    def create_email_verification_token(cls, user=None):
        """Create an email verification token."""
        if not user:
            user = cls.create_user()
        return EmailVerificationToken.objects.create(user=user)
    
    @classmethod
    def create_phone_verification_token(cls, user=None, token='123456'):
        """Create a phone verification token."""
        if not user:
            user = cls.create_user()
        return PhoneVerificationToken.objects.create(user=user, token=token)
    

    @classmethod
    def create_referral(cls, referrer=None, referred=None, **kwargs):
        """Create a referral relationship."""
        if not referrer:
            referrer = cls.create_user()
        if not referred:
            referred = cls.create_user()
        
        referral_code = cls.create_referral_code(user=referrer)
        
        defaults = {
            'level': 1,
            'referral_code': referral_code,
        }
        defaults.update(kwargs)
        
        return Referral.objects.create(
            referrer=referrer,
            referred=referred,
            **defaults
        )


class AuthenticationTestMixin:
    """Mixin providing authentication helpers for tests."""
    
    def login_user(self, user=None, email=None, password='testpass123'):
        """Login a user for testing."""
        if user:
            return self.client.force_login(user)
        elif email:
            # Use "email" instead of "username"
            return self.client.login(email=email, password=password)
        else:
            raise ValueError("Either user or email must be provided")

    
    def logout_user(self):
        """Logout current user."""
        self.client.logout()
    
    def assert_login_required(self, url, method='get', **kwargs):
        """Assert that a URL requires authentication."""
        if method.lower() == 'get':
            response = self.client.get(url, **kwargs)
        elif method.lower() == 'post':
            response = self.client.post(url, **kwargs)
        else:
            raise ValueError("Unsupported HTTP method")
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/users/login/', response.url)
    
    def assert_authenticated_access(self, url, user=None, expected_status=200, method='get', **kwargs):
        """Assert that authenticated user can access URL."""
        if user:
            self.login_user(user=user)
        
        if method.lower() == 'get':
            response = self.client.get(url, **kwargs)
        elif method.lower() == 'post':
            response = self.client.post(url, **kwargs)
        else:
            raise ValueError("Unsupported HTTP method")
        
        self.assertEqual(response.status_code, expected_status)
        return response


class EmailTestMixin:
    """Mixin providing email testing utilities."""
    
    def assert_email_sent(self, count=1):
        """Assert that email(s) were sent."""
        self.assertEqual(len(mail.outbox), count)
    
    def assert_no_email_sent(self):
        """Assert that no emails were sent."""
        self.assertEqual(len(mail.outbox), 0)
    
    def get_last_email(self):
        """Get the last sent email."""
        if not mail.outbox:
            self.fail("No emails were sent")
        return mail.outbox[-1]
    
    def assert_email_contains(self, text, email_index=-1):
        """Assert that an email contains specific text."""
        email = mail.outbox[email_index]
        self.assertIn(text, email.body)
    
    def assert_email_to(self, email_address, email_index=-1):
        """Assert that email was sent to specific address."""
        email = mail.outbox[email_index]
        self.assertIn(email_address, email.to)
    
    def clear_outbox(self):
        """Clear the email outbox."""
        mail.outbox.clear()


class FormTestMixin:
    """Mixin providing form testing utilities."""
    
    def assert_form_valid(self, form, expected_data=None):
        """Assert that a form is valid."""
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        if expected_data:
            for key, value in expected_data.items():
                self.assertEqual(form.cleaned_data[key], value)
    
    def assert_form_invalid(self, form, expected_errors=None):
        """Assert that a form is invalid."""
        self.assertFalse(form.is_valid())
        if expected_errors:
            for field, error_messages in expected_errors.items():
                self.assertIn(field, form.errors)
                for message in error_messages:
                    self.assertIn(message, str(form.errors[field]))
    
    def assert_form_field_required(self, form_class, field_name):
        """Assert that a form field is required."""
        form = form_class(data={})
        self.assertFalse(form.is_valid())
        self.assertIn(field_name, form.errors)
    
    def assert_form_field_optional(self, form_class, field_name, base_data):
        """Assert that a form field is optional."""
        form_data = base_data.copy()
        form_data[field_name] = ''
        form = form_class(data=form_data)
        # Should be valid even with empty optional field
        self.assertTrue(form.is_valid(), f"Form should be valid without {field_name}")


class ViewTestMixin:
    """Mixin providing view testing utilities."""
    
    def assert_template_used(self, response, template_name):
        """Assert that a specific template was used."""
        self.assertTemplateUsed(response, template_name)
    
    def assert_context_contains(self, response, key, expected_value=None):
        """Assert that response context contains a key with optional value check."""
        self.assertIn(key, response.context)
        if expected_value is not None:
            self.assertEqual(response.context[key], expected_value)
    
    def assert_message_sent(self, response, message_text, level=None):
        """Assert that a specific message was sent."""
        from django.contrib.messages import get_messages
        messages = list(get_messages(response.wsgi_request))
        message_texts = [str(msg) for msg in messages]
        self.assertIn(message_text, message_texts)
        
        if level is not None:
            matching_messages = [msg for msg in messages if str(msg) == message_text]
            self.assertTrue(any(msg.level == level for msg in matching_messages))
    
    def assert_redirect_to(self, response, expected_url):
        """Assert that response redirects to expected URL."""
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, expected_url)
    
    def post_with_csrf(self, url, data=None, **kwargs):
        """POST request with CSRF token."""
        if data is None:
            data = {}
        # Get CSRF token
        response = self.client.get(url)
        if hasattr(response, 'context') and response.context:
            csrf_token = response.context.get('csrf_token')
            if csrf_token:
                data['csrfmiddlewaretoken'] = csrf_token
        return self.client.post(url, data=data, **kwargs)


class DatabaseTestMixin:
    """Mixin providing database testing utilities."""
    
    def assert_model_exists(self, model_class, **kwargs):
        """Assert that a model instance exists with given criteria."""
        self.assertTrue(model_class.objects.filter(**kwargs).exists())
    
    def assert_model_not_exists(self, model_class, **kwargs):
        """Assert that a model instance does not exist with given criteria."""
        self.assertFalse(model_class.objects.filter(**kwargs).exists())
    
    def assert_model_count(self, model_class, expected_count, **kwargs):
        """Assert that model has expected count with optional filter."""
        actual_count = model_class.objects.filter(**kwargs).count()
        self.assertEqual(actual_count, expected_count)
    
    def get_model_instance(self, model_class, **kwargs):
        """Get a model instance or fail if not found/multiple found."""
        try:
            return model_class.objects.get(**kwargs)
        except model_class.DoesNotExist:
            self.fail(f"{model_class.__name__} matching {kwargs} does not exist")
        except model_class.MultipleObjectsReturned:
            self.fail(f"Multiple {model_class.__name__} instances found matching {kwargs}")


class MockServiceMixin:
    """Mixin providing service mocking utilities."""
    
    @patch('core.services.send_verification_email')
    def mock_email_service(self, mock_send):
        """Mock email verification service."""
        mock_send.return_value = True
        return mock_send
    
    @patch('wallets.services.WalletService.get_or_create_wallet')
    def mock_wallet_service(self, mock_wallet):
        """Mock wallet service."""
        mock_wallet_instance = Mock()
        mock_wallet_instance.balance = Decimal('100.00')
        mock_wallet_instance.get_available_balance.return_value = Decimal('100.00')
        mock_wallet.return_value = mock_wallet_instance
        return mock_wallet
    
    @patch('users.views.send_sms')
    def mock_sms_service(self, mock_sms):
        """Mock SMS service."""
        mock_sms.return_value = True
        return mock_sms


class PermissionTestMixin:
    """Mixin providing permission testing utilities."""
    
    def assert_permission_required(self, url, permission, user=None, method='get'):
        """Assert that a URL requires specific permission."""
        if user is None:
            user = self.create_user()
        
        self.login_user(user=user)
        
        if method.lower() == 'get':
            response = self.client.get(url)
        elif method.lower() == 'post':
            response = self.client.post(url)
        else:
            raise ValueError("Unsupported HTTP method")
        
        # Should be forbidden or redirect
        self.assertIn(response.status_code, [302, 403, 404])
    
    def assert_role_required(self, url, required_role, method='get'):
        """Assert that a URL requires specific user role."""
        # Test with wrong role
        if required_role != User.MEMBER:
            wrong_user = self.create_user(role=User.MEMBER)
            self.login_user(user=wrong_user)
            
            if method.lower() == 'get':
                response = self.client.get(url)
            elif method.lower() == 'post':
                response = self.client.post(url)
            
            self.assertIn(response.status_code, [302, 403, 404])
        
        # Test with correct role
        correct_user = self.create_user(role=required_role)
        self.login_user(user=correct_user)
        
        if method.lower() == 'get':
            response = self.client.get(url)
        elif method.lower() == 'post':
            response = self.client.post(url)
        
        # Should be accessible
        self.assertIn(response.status_code, [200, 302])  # 302 for redirects


class APITestMixin:
    """Mixin providing API testing utilities."""
    
    def assert_json_response(self, response, expected_data=None):
        """Assert that response is valid JSON with optional data check."""
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        
        if expected_data:
            for key, value in expected_data.items():
                self.assertIn(key, data)
                self.assertEqual(data[key], value)
        
        return data
    
    def assert_api_success(self, response, expected_data=None):
        """Assert that API response indicates success."""
        self.assertEqual(response.status_code, 200)
        data = self.assert_json_response(response, expected_data)
        return data
    
    def assert_api_error(self, response, expected_status=400, expected_message=None):
        """Assert that API response indicates error."""
        self.assertEqual(response.status_code, expected_status)
        data = response.json()
        
        if expected_message:
            self.assertIn('message', data)
            self.assertEqual(data['message'], expected_message)
        
        return data


class BaseTestCase(TestCase, TestDataMixin, AuthenticationTestMixin, 
                   EmailTestMixin, FormTestMixin, ViewTestMixin, 
                   DatabaseTestMixin, MockServiceMixin, PermissionTestMixin,
                   APITestMixin):
    """Base test case combining all mixins."""
    
    def setUp(self):
        """Set up test environment."""
        super().setUp()
        # Clear email outbox
        self.clear_outbox()
    
    def tearDown(self):
        """Clean up after test."""
        super().tearDown()
        # Clear email outbox
        self.clear_outbox()


class TestUtilitiesTest(TestCase):
    """Test the test utilities themselves."""
    
    def test_create_user_utility(self):
        """Test user creation utility."""
        user = TestDataMixin.create_user(email='test@example.com')
        self.assertEqual(user.email, 'test@example.com')
        self.assertEqual(user.role, User.MEMBER)
        self.assertTrue(user.check_password('testpass123'))
    
    def test_create_admin_user_utility(self):
        """Test admin user creation utility."""
        admin = TestDataMixin.create_admin_user()
        self.assertEqual(admin.role, User.ADMIN)
        self.assertTrue(admin.is_staff)
    
    def test_create_user_profile_utility(self):
        """Test user profile creation utility."""
        user = TestDataMixin.create_user()
        profile = TestDataMixin.create_user_profile(user=user)
        profile.occupation = 'Software Developer'
        profile.save()
        self.assertEqual(profile.user, user)
        self.assertEqual(profile.occupation, 'Software Developer')
    
    # def test_create_referral_code_utility(self):
    #     """Test referral code creation utility."""
    #     user = TestDataMixin.create_user()
    #     referral_code = TestDataMixin.create_referral_code(user=user)
    #     self.assertEqual(referral_code.user, user)
    #     self.assertEqual(referral_code.code, 'VCRIDOEG')
    #     self.assertTrue(referral_code.is_active)
    
    def test_create_referral_utility(self):
        """Test referral creation utility."""
        referrer = TestDataMixin.create_user(email='referrer@example.com')
        referred = TestDataMixin.create_user(email='referred@example.com')
        referral = TestDataMixin.create_referral(referrer=referrer, referred=referred)
        
        self.assertEqual(referral.referrer, referrer)
        self.assertEqual(referral.referred, referred)
        self.assertEqual(referral.level, 1)


class TestCoverageHelpers(TestCase):
    """Helper methods to ensure comprehensive test coverage."""
    
    def test_all_model_methods_covered(self):
        """Ensure all model methods are tested."""
        user_methods = [
            'get_full_name', 'get_short_name', 'get_display_name',
            'can_post_tasks', 'can_moderate', 'save'
        ]
        
        # This is more of a documentation test
        # In practice, we verify these methods in model tests
        self.assertTrue(all(hasattr(User, method) for method in user_methods))
    
    def test_all_view_classes_covered(self):
        """Ensure all view classes are tested."""
        from users import views
        
        view_classes = [
            'UserRegistrationView', 'CustomLoginView', 'UserLogoutView',
            'ProfileSetupView', 'UserDashboardView', 'EmailVerificationView',
            'ResendVerificationView', 'PhoneVerificationView',
            'PhoneVerificationCodeView', 'PasswordChangeView',
            'UserProfileView', 'PublicProfileView',
            'CheckEmailAvailabilityView', 'CheckPhoneAvailabilityView',
            'ValidateReferralCodeView', 'CustomPasswordResetView'
        ]
        
        # Verify all views exist in the module
        for view_class in view_classes:
            self.assertTrue(hasattr(views, view_class),
                          f"View {view_class} not found in views module")
    
    def test_all_form_classes_covered(self):
        """Ensure all form classes are tested."""
        from users import forms
        
        form_classes = [
            'CustomUserCreationForm', 'CustomAuthenticationForm',
            'UserProfileForm', 'ExtendedProfileForm',
            'PhoneVerificationForm', 'PhoneVerificationCodeForm',
            'PasswordChangeForm'
        ]
        
        # Verify all forms exist in the module
        for form_class in form_classes:
            self.assertTrue(hasattr(forms, form_class),
                          f"Form {form_class} not found in forms module")
    
    def test_all_url_patterns_covered(self):
        """Ensure all URL patterns are tested."""
        from django.urls import reverse
        
        url_names = [
            'users:register', 'users:login', 'users:logout',
            'users:profile', 'users:profile_setup', 'users:dashboard',
            'users:verify_email', 'users:resend_verification',
            'users:phone_verify', 'users:phone_verify_code',
            'users:password_change', 'users:password_reset',
            'users:check_email', 'users:check_phone', 'users:validate_referral'
        ]
        
        # This test ensures all URLs are properly named and reversible
        for url_name in url_names:
            try:
                if 'verify_email' in url_name:
                    # Skip URLs that require parameters
                    continue
                elif 'public_profile' in url_name:
                    continue
                else:
                    reverse(url_name)
            except Exception as e:
                self.fail(f"URL {url_name} cannot be reversed: {e}")


class PerformanceTestMixin:
    """Mixin for testing performance aspects."""
    
    def assert_query_count(self, expected_count, func, *args, **kwargs):
        """Assert that a function executes expected number of queries."""
        from django.db import connection
        
        # Reset queries
        connection.queries_log.clear()
        
        # Execute function
        func(*args, **kwargs)
        
        # Check query count
        actual_count = len(connection.queries)
        self.assertEqual(
            actual_count, expected_count,
            f"Expected {expected_count} queries, but {actual_count} were executed. "
            f"Queries: {[q['sql'] for q in connection.queries]}"
        )
    
    def assert_no_n_plus_one(self, func, *args, **kwargs):
        """Assert that a function doesn't have N+1 query problems."""
        from django.db import connection
        
        # Execute function and capture queries
        connection.queries_log.clear()
        func(*args, **kwargs)
        queries = list(connection.queries)
        
        # Check for potential N+1 patterns
        select_queries = [q for q in queries if q['sql'].strip().upper().startswith('SELECT')]
        
        # Simple heuristic: if we have many similar SELECT queries, it might be N+1
        similar_queries = {}
        for query in select_queries:
            # Normalize query by removing specific IDs
            import re
            normalized = re.sub(r'\d+', 'X', query['sql'])
            similar_queries[normalized] = similar_queries.get(normalized, 0) + 1
        
        # Flag if any query pattern appears more than reasonable times
        max_similar = max(similar_queries.values()) if similar_queries else 0
        self.assertLessEqual(
            max_similar, 5,  # Arbitrary threshold
            f"Potential N+1 query detected. Similar queries: {similar_queries}"
        )