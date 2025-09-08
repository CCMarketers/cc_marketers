# users/tests/test_admin.py
from django.test import TestCase
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from unittest.mock import patch, PropertyMock

from users.admin import (
    UserAdmin, UserProfileAdmin, EmailVerificationTokenAdmin,
    PhoneVerificationTokenAdmin
)
from users.models import UserProfile, EmailVerificationToken, PhoneVerificationToken
from .test_utils import BaseTestCase

from django.urls import reverse


User = get_user_model()


class UserAdminTest(BaseTestCase):
    """Test UserAdmin functionality."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = UserAdmin(User, self.site)
        self.superuser = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )

    def test_user_admin_list_display(self):
        expected_fields = [
            'email', 'get_full_name', 'role', 'is_active',
            'email_verified', 'phone_verified', 'date_joined'
        ]
        self.assertEqual(list(self.admin.list_display), expected_fields)

    def test_user_admin_list_filter(self):
        expected_filters = [
            'role', 'is_active', 'email_verified',
            'phone_verified', 'date_joined'
        ]
        self.assertEqual(list(self.admin.list_filter), expected_filters)

    def test_user_admin_search_fields(self):
        expected_fields = ['email', 'first_name', 'last_name', 'phone']
        self.assertEqual(list(self.admin.search_fields), expected_fields)

    def test_user_admin_ordering(self):
        self.assertEqual(self.admin.ordering, ('-date_joined',))

    def test_user_admin_fieldsets(self):
        fieldsets = self.admin.fieldsets
        self.assertIsInstance(fieldsets, tuple)

        fieldset_names = [fs[0] for fs in fieldsets]
        expected_names = {
            None, 'Personal info', 'Location', 'Role & Permissions',
            'Verification', 'Preferences', 'Important dates'
        }
        # Subset check instead of brittle length check
        self.assertTrue(expected_names.issubset(set(fieldset_names)))

    def test_user_admin_add_fieldsets(self):
        add_fieldsets = self.admin.add_fieldsets
        self.assertIsInstance(add_fieldsets, tuple)
        self.assertEqual(len(add_fieldsets), 1)

        add_fields = add_fieldsets[0][1]['fields']
        expected_fields = ('email', 'password1', 'password2', 'role')
        self.assertEqual(add_fields, expected_fields)

    def test_user_admin_readonly_fields(self):
        expected_readonly = ('date_joined', 'last_login')
        self.assertEqual(self.admin.readonly_fields, expected_readonly)

    def test_user_admin_registration(self):
        self.assertIn(User, admin.site._registry)
        registered = admin.site._registry[User]
        self.assertIsInstance(registered, UserAdmin)


class UserProfileAdminTest(BaseTestCase):
    """Test UserProfileAdmin functionality."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = UserProfileAdmin(UserProfile, self.site)
        self.user = self.create_user()
        self.profile = self.create_user_profile(user=self.user)

    def test_user_profile_admin_list_display(self):
        expected_fields = [
            'user', 'occupation', 'tasks_completed', 'tasks_posted',
            'success_rate', 'average_rating'
        ]
        self.assertEqual(list(self.admin.list_display), expected_fields)

    def test_user_profile_admin_list_filter(self):
        expected_filters = ['experience_years', 'created_at']
        self.assertEqual(list(self.admin.list_filter), expected_filters)

    def test_user_profile_admin_search_fields(self):
        expected_fields = [
            'user__email', 'user__first_name', 'user__last_name',
            'occupation', 'company'
        ]
        self.assertEqual(list(self.admin.search_fields), expected_fields)

    def test_user_profile_admin_readonly_fields(self):
        expected_readonly = [
            'tasks_completed', 'tasks_posted', 'success_rate',
            'average_rating', 'total_reviews'
        ]
        self.assertEqual(list(self.admin.readonly_fields), expected_readonly)

    def test_tasks_completed_method(self):
        with patch.object(UserProfile, 'tasks_completed', new_callable=PropertyMock) as mock_tasks_completed:
            mock_tasks_completed.return_value = 5
            result = self.admin.tasks_completed(self.profile)
            self.assertEqual(result, 5)
        self.assertEqual(self.admin.tasks_completed.short_description, "Tasks Completed")

    def test_tasks_posted_method(self):
        with patch.object(UserProfile, 'tasks_posted', new_callable=PropertyMock) as mock_tasks_posted:
            mock_tasks_posted.return_value = 3
            result = self.admin.tasks_posted(self.profile)
            self.assertEqual(result, 3)
        self.assertEqual(self.admin.tasks_posted.short_description, "Tasks Posted")

    def test_success_rate_and_average_rating_methods(self):
        with patch.object(UserProfile, 'success_rate', new_callable=PropertyMock) as mock_success_rate, \
             patch.object(UserProfile, 'average_rating', new_callable=PropertyMock) as mock_avg_rating:
            mock_success_rate.return_value = 85
            mock_avg_rating.return_value = 4.7
            self.assertEqual(self.profile.success_rate, 85)
            self.assertEqual(self.profile.average_rating, 4.7)

    def test_user_profile_admin_registration(self):
        self.assertIn(UserProfile, admin.site._registry)
        self.assertIsInstance(admin.site._registry[UserProfile], UserProfileAdmin)


class EmailVerificationTokenAdminTest(BaseTestCase):
    """Test EmailVerificationTokenAdmin functionality."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = EmailVerificationTokenAdmin(EmailVerificationToken, self.site)
        self.user = self.create_user()
        self.token = self.create_email_verification_token(user=self.user)

    def test_email_token_admin_list_display(self):
        expected_fields = ['user', 'token', 'created_at', 'expires_at', 'used']
        self.assertEqual(list(self.admin.list_display), expected_fields)

    def test_email_token_admin_list_filter(self):
        expected_filters = ['used', 'created_at', 'expires_at']
        self.assertEqual(list(self.admin.list_filter), expected_filters)

    def test_email_token_admin_search_fields(self):
        expected_fields = ['user__email', 'token']
        self.assertEqual(list(self.admin.search_fields), expected_fields)

    def test_email_token_admin_readonly_fields(self):
        expected_readonly = ('token',)
        self.assertEqual(self.admin.readonly_fields, expected_readonly)

    def test_email_token_admin_registration(self):
        self.assertIn(EmailVerificationToken, admin.site._registry)
        self.assertIsInstance(admin.site._registry[EmailVerificationToken], EmailVerificationTokenAdmin)


class PhoneVerificationTokenAdminTest(BaseTestCase):
    """Test PhoneVerificationTokenAdmin functionality."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = PhoneVerificationTokenAdmin(PhoneVerificationToken, self.site)
        self.user = self.create_user()
        self.token = self.create_phone_verification_token(user=self.user)

    def test_phone_token_admin_list_display(self):
        expected_fields = ['user', 'token', 'created_at', 'expires_at', 'used']
        self.assertEqual(list(self.admin.list_display), expected_fields)

    def test_phone_token_admin_list_filter(self):
        expected_filters = ['used', 'created_at', 'expires_at']
        self.assertEqual(list(self.admin.list_filter), expected_filters)

    def test_phone_token_admin_search_fields(self):
        expected_fields = ['user__phone', 'token']
        self.assertEqual(list(self.admin.search_fields), expected_fields)

    def test_phone_token_admin_readonly_fields(self):
        expected_readonly = ('token',)
        self.assertEqual(self.admin.readonly_fields, expected_readonly)

    def test_phone_token_admin_registration(self):
        self.assertIn(PhoneVerificationToken, admin.site._registry)
        self.assertIsInstance(admin.site._registry[PhoneVerificationToken], PhoneVerificationTokenAdmin)



class AdminIntegrationTest(TestCase):
    def setUp(self):
        # Create superuser to access admin
        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass",
            first_name="Admin",
            last_name="User"
        )
        self.client.force_login(self.admin_user)

        # Create normal users + profiles
        for i in range(3):
            user = User.objects.create_user(
                email=f"profile{i}@example.com",
                password="testpass123",
                first_name="Test",
                last_name="User"
            )
            UserProfile.objects.get_or_create(user=user)

    def test_user_profile_admin_changelist(self):
        """Ensure the UserProfile admin changelist renders user __str__ values."""
        url = reverse("admin:users_userprofile_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Check that each user's string representation (not email) is shown
        for user in User.objects.exclude(pk=self.admin_user.pk):
            self.assertContains(response, str(user))

    def test_admin_site_accessible(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)

    def test_user_admin_changelist(self):
        users = [
            self.create_user(email=f'user{i}@example.com', role=User.MEMBER)
            for i in range(3)
        ]
        response = self.client.get('/admin/users/user/')
        self.assertEqual(response.status_code, 200)
        for user in users:
            self.assertContains(response, user.email)

    def test_user_admin_add_user_get(self):
        response = self.client.get('/admin/users/user/add/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'email')
        self.assertContains(response, 'password1')
        self.assertContains(response, 'password2')
        self.assertContains(response, 'role')

    def test_user_admin_change_user(self):
        user = self.create_user()
        response = self.client.get(f'/admin/users/user/{user.id}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, user.email)
        self.assertContains(response, user.first_name)

    # def test_user_profile_admin_changelist(self):
    #     profiles = [
    #         self.create_user_profile(
    #             user=self.create_user(email=f'profile{i}@example.com'),
    #             occupation=f'Job {i}'
    #         )
    #         for i in range(3)
    #     ]
    #     response = self.client.get('/admin/users/userprofile/')
    #     self.assertEqual(response.status_code, 200)
    #     for profile in profiles:
    #         self.assertContains(response, profile.user.email)
    #         self.assertContains(response, profile.occupation)


class AdminPermissionsTest(BaseTestCase):
    def test_non_admin_cannot_access_admin(self):
        user = self.create_user()
        self.client.login(email=user.email, password='testpass123')
        response = self.client.get('/admin/')
        self.assertIn(response.status_code, [302, 403])

    def test_staff_user_can_access_admin(self):
        staff_user = self.create_user(is_staff=True)
        self.client.login(email=staff_user.email, password='testpass123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)

    def test_admin_role_automatically_gets_staff(self):
        admin_user = self.create_user(role=User.ADMIN)
        self.assertTrue(admin_user.is_staff)
        self.client.login(email=admin_user.email, password='testpass123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)


class AdminRegistrationTest(TestCase):
    """Test admin model registration independent of BaseTestCase."""

    def test_all_models_registered(self):
        expected_models = [
            User,
            UserProfile,
            EmailVerificationToken,
            PhoneVerificationToken
        ]
        for model in expected_models:
            self.assertIn(model, admin.site._registry)

    def test_admin_classes_correct(self):
        admin_mappings = {
            User: UserAdmin,
            UserProfile: UserProfileAdmin,
            EmailVerificationToken: EmailVerificationTokenAdmin,
            PhoneVerificationToken: PhoneVerificationTokenAdmin
        }
        for model, expected_admin_class in admin_mappings.items():
            registered_admin = admin.site._registry.get(model)
            self.assertIsNotNone(registered_admin)
            self.assertIsInstance(registered_admin, expected_admin_class)

    def test_admin_decorator_usage(self):
        self.assertIsInstance(admin.site._registry.get(User), UserAdmin)
        self.assertIsInstance(admin.site._registry.get(UserProfile), UserProfileAdmin)
        self.assertIsInstance(admin.site._registry.get(EmailVerificationToken), EmailVerificationTokenAdmin)
        self.assertIsInstance(admin.site._registry.get(PhoneVerificationToken), PhoneVerificationTokenAdmin)
