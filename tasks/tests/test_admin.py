# tests/test_admin.py
"""
Test suite for Django admin configuration of task models.
Tests admin interface, permissions, and custom configurations.
"""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.urls import reverse

from tasks.admin import (
    TaskAdmin, SubmissionAdmin, DisputeAdmin, 
    TaskWalletAdmin, TaskWalletTransactionAdmin
)
from tasks.models import Task, Submission, Dispute, TaskWallet, TaskWalletTransaction
from .test_base import ComprehensiveTaskTestCase


import uuid
from django.contrib.auth.hashers import make_password

User = get_user_model()


class TaskAdminTest(ComprehensiveTaskTestCase):
    """Test cases for TaskAdmin configuration."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin_obj = TaskAdmin(Task, self.site)

    def test_list_display_configuration(self):
        """Test that list_display is configured correctly."""
        expected_fields = ['title', 'advertiser', 'payout_per_slot', 'remaining_slots', 
                          'total_slots', 'deadline', 'status']
        self.assertEqual(list(self.admin_obj.list_display), expected_fields)

    def test_list_filter_configuration(self):
        """Test that list_filter is configured correctly."""
        expected_filters = ['status', 'created_at', 'deadline']
        self.assertEqual(list(self.admin_obj.list_filter), expected_filters)

    def test_search_fields_configuration(self):
        """Test that search_fields is configured correctly."""
        expected_fields = ['title', 'description', 'advertiser__username']
        self.assertEqual(list(self.admin_obj.search_fields), expected_fields)

    def test_readonly_fields_configuration(self):
        """Test that readonly_fields is configured correctly."""
        expected_fields = ['created_at', 'updated_at']
        self.assertEqual(list(self.admin_obj.readonly_fields), expected_fields)

    def test_task_admin_queryset(self):
        """Test admin queryset includes all necessary data."""
        # Create test tasks
        task1 = self.create_task(title='Task 1')
        task2 = self.create_task(title='Task 2', status='paused')
        
        # Get admin queryset
        request = type('MockRequest', (), {'user': self.admin})()
        queryset = self.admin_obj.get_queryset(request)
        
        # Should include all tasks
        self.assertIn(task1, queryset)
        self.assertIn(task2, queryset)

    def test_task_admin_permissions(self):
        """Test admin permissions for task operations."""
        # Make sure self.admin has proper permissions
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()

        # Create a mock request with this admin user
        request = type('MockRequest', (), {'user': self.admin})()

        # Test permissions
        self.assertTrue(self.admin_obj.has_view_permission(request))
        self.assertTrue(self.admin_obj.has_add_permission(request))
        self.assertTrue(self.admin_obj.has_change_permission(request))
        self.assertTrue(self.admin_obj.has_delete_permission(request))



class SubmissionAdminTest(ComprehensiveTaskTestCase):
    """Test cases for SubmissionAdmin configuration."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin_obj = SubmissionAdmin(Submission, self.site)

    def test_list_display_configuration(self):
        """Test that list_display is configured correctly."""
        expected_fields = ['task', 'member', 'status', 'submitted_at', 'reviewed_by']
        self.assertEqual(list(self.admin_obj.list_display), expected_fields)

    def test_list_filter_configuration(self):
        """Test that list_filter is configured correctly."""
        expected_filters = ['status', 'submitted_at', 'reviewed_at']
        self.assertEqual(list(self.admin_obj.list_filter), expected_filters)

    def test_search_fields_configuration(self):
        """Test that search_fields is configured correctly."""
        expected_fields = ['task__title', 'member__username']
        self.assertEqual(list(self.admin_obj.search_fields), expected_fields)

    def test_readonly_fields_configuration(self):
        """Test that readonly_fields is configured correctly."""
        expected_fields = ['submitted_at', 'reviewed_at']
        self.assertEqual(list(self.admin_obj.readonly_fields), expected_fields)


class DisputeAdminTest(ComprehensiveTaskTestCase):
    """Test cases for DisputeAdmin configuration."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin_obj = DisputeAdmin(Dispute, self.site)

    def test_list_display_configuration(self):
        """Test that list_display is configured correctly."""
        expected_fields = ['id', 'submission', 'raised_by', 'status', 'created_at', 'resolved_by']
        self.assertEqual(list(self.admin_obj.list_display), expected_fields)

    def test_list_filter_configuration(self):
        """Test that list_filter is configured correctly."""
        expected_filters = ['status', 'created_at', 'resolved_at']
        self.assertEqual(list(self.admin_obj.list_filter), expected_filters)

    def test_search_fields_configuration(self):
        """Test that search_fields is configured correctly."""
        expected_fields = ['submission__task__title', 'raised_by__username']
        self.assertEqual(list(self.admin_obj.search_fields), expected_fields)

    def test_readonly_fields_configuration(self):
        """Test that readonly_fields is configured correctly."""
        expected_fields = ['created_at', 'resolved_at']
        self.assertEqual(list(self.admin_obj.readonly_fields), expected_fields)


class TaskWalletAdminTest(ComprehensiveTaskTestCase):
    """Test cases for TaskWalletAdmin configuration."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin_obj = TaskWalletAdmin(TaskWallet, self.site)

    def test_list_display_configuration(self):
        """Test that list_display is configured correctly."""
        expected_fields = ['user', 'balance', 'created_at', 'updated_at']
        self.assertEqual(list(self.admin_obj.list_display), expected_fields)

    def test_search_fields_configuration(self):
        """Test that search_fields is configured correctly."""
        expected_fields = ['user__username']
        self.assertEqual(list(self.admin_obj.search_fields), expected_fields)

    def test_readonly_fields_configuration(self):
        """Test that readonly_fields is configured correctly."""
        expected_fields = ['created_at', 'updated_at']
        self.assertEqual(list(self.admin_obj.readonly_fields), expected_fields)


class TaskWalletTransactionAdminTest(ComprehensiveTaskTestCase):
    """Test cases for TaskWalletTransactionAdmin configuration."""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin_obj = TaskWalletTransactionAdmin(TaskWalletTransaction, self.site)

    def test_list_display_configuration(self):
        """Test that list_display is configured correctly."""
        expected_fields = ['user', 'transaction_type', 'category', 'amount', 'status', 'created_at']
        self.assertEqual(list(self.admin_obj.list_display), expected_fields)

    def test_list_filter_configuration(self):
        """Test that list_filter is configured correctly."""
        expected_filters = ['transaction_type', 'category', 'status', 'created_at']
        self.assertEqual(list(self.admin_obj.list_filter), expected_filters)

    def test_search_fields_configuration(self):
        """Test that search_fields is configured correctly."""
        expected_fields = ['user__username', 'reference']
        self.assertEqual(list(self.admin_obj.search_fields), expected_fields)

    def test_readonly_fields_configuration(self):
        """Test that readonly_fields is configured correctly."""
        expected_fields = ['created_at']
        self.assertEqual(list(self.admin_obj.readonly_fields), expected_fields)




class AdminIntegrationTest(ComprehensiveTaskTestCase):
    """Integration tests for admin interface."""

    def setUp(self):
        super().setUp()

        # Ensure unique username per test run
        username = f'admin_{uuid.uuid4().hex[:6]}'
        self.admin_user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': f'{username}@test.com',
                'password': make_password('admin123'),  # hash the password
                'is_superuser': True,
                'is_staff': True,
            }
        )



    def test_admin_task_list_view(self):
        """Test admin task list view."""
        self.client.force_login(self.admin_user)
        
        # Create test tasks
        self.create_task(title='Admin Test Task 1')
        self.create_task(title='Admin Test Task 2', status='paused')
        
        url = reverse('admin:tasks_task_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin Test Task 1')
        self.assertContains(response, 'Admin Test Task 2')

    def test_admin_task_detail_view(self):
        """Test admin task detail view."""
        self.client.force_login(self.admin_user)

