# tests/test_views_auth.py
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages

from referrals.models import  Referral
from .test_base import BaseTestCase, MockTestCase

User = get_user_model()


class UserRegistrationViewTests(MockTestCase):
    """Tests for UserRegistrationView"""

    def setUp(self):
        super().setUp()
        self.url = reverse('users:register')
        self.valid_data = {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': User.MEMBER,
        }

    def test_get_registration_form(self):
        """Test GET request returns registration form"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register')
        self.assertContains(response, 'form')

    def test_successful_registration(self):
        """Test successful user registration"""
        response = self.client.post(self.url, data=self.valid_data)
        
        # Check user was created
        self.assertTrue(User.objects.filter(email='test@example.com').exists())
        
        user = User.objects.get(email='test@example.com')
        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'User')
        self.assertEqual(user.role, User.MEMBER)
        
        # Check user is logged in
        self.assertTrue(user.is_authenticated)
        
        # Check verification email was sent
        self.mock_email.assert_called_once_with(user)
        
        # Check redirect
        self.assertRedirects(response, reverse('users:profile_setup'))
        
        # Check success message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Welcome' in str(m) for m in messages))

    def test_registration_with_referral_code_in_url(self):
        """Test registration with referral code from URL"""
        referrer = self.create_user(email='referrer@example.com')
        referral_code = self.create_referral_code(user=referrer)
        
        url_with_ref = f"{self.url}?ref={referral_code.code}"
        response = self.client.get(url_with_ref)
        
        # Check referral code is pre-filled
        self.assertContains(response, f'value="{referral_code.code}"')

    def test_registration_creates_referral_relationship(self):
        """Test registration creates referral relationship"""
        referrer = self.create_user(email='referrer@example.com')
        referral_code = self.create_referral_code(user=referrer)
        
        data = self.valid_data.copy()
        data['referral_code'] = referral_code.code
        
        self.client.post(self.url, data=data)
        
        # Check referral was created
        self.assertTrue(Referral.objects.filter(
            referrer=referrer,
            referred__email='test@example.com'
        ).exists())

    def test_registration_with_referral_in_url_param(self):
        """Test registration with referral code in URL parameter"""
        referrer = self.create_user(email='referrer@example.com')
        referral_code = self.create_referral_code(user=referrer)
        
        url_with_ref = f"{self.url}?ref={referral_code.code}"
        self.client.post(url_with_ref, data=self.valid_data)
        
        # Check referral was created
        self.assertTrue(Referral.objects.filter(
            referrer=referrer,
            referred__email='test@example.com'
        ).exists())

    def test_registration_with_invalid_referral_code(self):
        """Test registration with invalid referral code"""
        data = self.valid_data.copy()
        data['referral_code'] = 'INVALID123'
        
        response = self.client.post(self.url, data=data)
        
        # Form should have errors
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'referral_code', 
                           'Invalid referral code.')

    def test_registration_ignores_nonexistent_referral_in_url(self):
        """Test registration ignores nonexistent referral code in URL"""
        url_with_ref = f"{self.url}?ref=NONEXISTENT"
        response = self.client.post(url_with_ref, data=self.valid_data)
        
        # Should still succeed
        self.assertRedirects(response, reverse('users:profile_setup'))
        
        # No referral should be created
        user = User.objects.get(email='test@example.com')
        self.assertFalse(Referral.objects.filter(referred=user).exists())

    def test_registration_duplicate_email(self):
        """Test registration with duplicate email"""
        # Create existing user
        self.create_user(email='test@example.com')
        
        response = self.client.post(self.url, data=self.valid_data)
        
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'email', 
                           'A user with this email already exists.')

    def test_registration_password_mismatch(self):
        """Test registration with password mismatch"""
        data = self.valid_data.copy()
        data['password2'] = 'differentpass'
        
        response = self.client.post(self.url, data=data)
        
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response, 'form', 'password2', None)

    def test_registration_missing_required_fields(self):
        """Test registration with missing required fields"""
        response = self.client.post(self.url, data={})
        
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        
        required_fields = ['email', 'first_name', 'last_name', 'password1', 'password2']
        for field in required_fields:
            self.assertIn(field, form.errors)


class CustomLoginViewTests(BaseTestCase):
    """Tests for CustomLoginView"""

    def setUp(self):
        super().setUp()
        self.url = reverse('users:login')
        self.user = self.create_user(
            email='test@example.com',
            phone='+1234567890'
        )

    def test_get_login_form(self):
        """Test GET request returns login form"""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login')
        self.assertContains(response, 'form')

    def test_login_with_email(self):
        """Test login with email"""
        data = {
            'username': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post(self.url, data=data)
        
        # Check user is logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user, self.user)

    def test_login_with_phone(self):
        """Test login with phone number"""
        data = {
            'username': '+1234567890',
            'password': 'testpass123'
        }
        
        response = self.client.post(self.url, data=data)
        
        # Check user is logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.wsgi_request.user, self.user)

    def test_login_success_message(self):
        """Test success message after login"""
        data = {
            'username': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post(self.url, data=data, follow=True)
        
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Welcome back' in str(m) for m in messages))

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        data = {
            'username': 'test@example.com',
            'password': 'wrongpass'
        }
        
        response = self.client.post(self.url, data=data)
        
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Invalid login credentials' in str(m) for m in messages))

    def test_login_nonexistent_user(self):
        """Test login with nonexistent user"""
        data = {
            'username': 'nonexistent@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post(self.url, data=data)
        
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_redirect_authenticated_user(self):
        """Test authenticated user is redirected"""
        self.login_user(self.user)
        
        response = self.client.get(self.url)
        
        # Should redirect away from login page
        self.assertEqual(response.status_code, 302)

    def test_login_redirect_next_url(self):
        """Test login redirects to next URL"""
        next_url = reverse('users:profile')
        url_with_next = f"{self.url}?next={next_url}"
        
        data = {
            'username': 'test@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post(url_with_next, data=data)
        
        self.assertRedirects(response, next_url)

    def test_login_redirect_by_role_member(self):
        """Test login redirects member to task list"""
        self.create_member_user(email='member@example.com')
        
        data = {
            'username': 'member@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post(self.url, data=data)
        
        self.assertRedirects(response, reverse('tasks:task_list'))

    def test_login_redirect_by_role_advertiser(self):
        """Test login redirects advertiser to my tasks"""
        self.create_advertiser_user(email='advertiser@example.com')
        
        data = {
            'username': 'advertiser@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post(self.url, data=data)
        
        self.assertRedirects(response, reverse('tasks:my_tasks'))

    def test_login_redirect_by_role_admin(self):
        """Test login redirects admin to dashboard"""
        self.create_admin_user(email='admin@example.com')
        
        data = {
            'username': 'admin@example.com',
            'password': 'testpass123'
        }
        
        response = self.client.post(self.url, data=data)
        
        self.assertRedirects(response, reverse('users:dashboard'))


class UserLogoutViewTests(BaseTestCase):
    """Tests for UserLogoutView"""

    def setUp(self):
        super().setUp()
        self.url = reverse('users:logout')
        self.user = self.create_user()

    def test_logout_authenticated_user(self):
        """Test logout for authenticated user"""
        self.login_user(self.user)
        
        # Verify user is logged in
        self.assertTrue(self.client.session.get('_auth_user_id'))
        
        response = self.client.get(self.url)
        
        # Check redirect to login page
        self.assertRedirects(response, reverse('users:login'))
        
        # Check user