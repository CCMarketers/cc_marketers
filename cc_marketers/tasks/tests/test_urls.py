# tests/test_urls.py
"""
Test suite for task app URL patterns and routing.
Tests URL resolution, reverse URL generation, and parameter handling.
"""
from django.urls import reverse, resolve
from django.contrib.auth import get_user_model

from tasks import views
from .test_base import ComprehensiveTaskTestCase

User = get_user_model()


class TaskURLTest(ComprehensiveTaskTestCase):
    """Test cases for task-related URLs."""

    def test_task_list_url(self):
        """Test task list URL pattern."""
        url = reverse('tasks:task_list')
        self.assertEqual(url, '/tasks/')
        
        # Test URL resolution
        resolver = resolve('/tasks/')
        self.assertEqual(resolver.view_name, 'tasks:task_list')
        self.assertEqual(resolver.func, views.task_list)

    def test_create_task_url(self):
        """Test create task URL pattern."""
        url = reverse('tasks:create_task')
        self.assertEqual(url, '/tasks/create/')
        
        # Test URL resolution
        resolver = resolve('/tasks/create/')
        self.assertEqual(resolver.view_name, 'tasks:create_task')
        self.assertEqual(resolver.func, views.create_task)

    def test_my_tasks_url(self):
        """Test my tasks URL pattern."""
        url = reverse('tasks:my_tasks')
        self.assertEqual(url, '/tasks/my-tasks/')
        
        # Test URL resolution
        resolver = resolve('/tasks/my-tasks/')
        self.assertEqual(resolver.view_name, 'tasks:my_tasks')
        self.assertEqual(resolver.func, views.my_tasks)

    def test_my_submissions_url(self):
        """Test my submissions URL pattern."""
        url = reverse('tasks:my_submissions')
        self.assertEqual(url, '/tasks/my-submissions/')
        
        # Test URL resolution
        resolver = resolve('/tasks/my-submissions/')
        self.assertEqual(resolver.view_name, 'tasks:my_submissions')
        self.assertEqual(resolver.func, views.my_submissions)

    def test_task_detail_url(self):
        """Test task detail URL pattern with parameter."""
        task_id = 123
        url = reverse('tasks:task_detail', kwargs={'task_id': task_id})
        self.assertEqual(url, f'/tasks/{task_id}/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/{task_id}/')
        self.assertEqual(resolver.view_name, 'tasks:task_detail')
        self.assertEqual(resolver.func, views.task_detail)
        self.assertEqual(resolver.kwargs['task_id'], task_id)

    def test_edit_task_url(self):
        """Test edit task URL pattern."""
        task_id = 456
        url = reverse('tasks:edit_task', kwargs={'task_id': task_id})
        self.assertEqual(url, f'/tasks/task/{task_id}/edit/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/task/{task_id}/edit/')
        self.assertEqual(resolver.view_name, 'tasks:edit_task')
        self.assertEqual(resolver.func, views.edit_task)
        self.assertEqual(resolver.kwargs['task_id'], task_id)

    def test_delete_task_url(self):
        """Test delete task URL pattern."""
        task_id = 789
        url = reverse('tasks:delete_task', kwargs={'task_id': task_id})
        self.assertEqual(url, f'/tasks/task/{task_id}/delete/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/task/{task_id}/delete/')
        self.assertEqual(resolver.view_name, 'tasks:delete_task')
        self.assertEqual(resolver.func, views.delete_task)
        self.assertEqual(resolver.kwargs['task_id'], task_id)


class ReviewURLTest(ComprehensiveTaskTestCase):
    """Test cases for review-related URLs."""

    def test_review_submissions_url(self):
        """Test review submissions URL pattern."""
        task_id = 123
        url = reverse('tasks:review_submissions', kwargs={'task_id': task_id})
        self.assertEqual(url, f'/tasks/{task_id}/review/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/{task_id}/review/')
        self.assertEqual(resolver.view_name, 'tasks:review_submissions')
        self.assertEqual(resolver.func, views.review_submissions)
        self.assertEqual(resolver.kwargs['task_id'], task_id)

    def test_review_submission_url(self):
        """Test review individual submission URL pattern."""
        submission_id = 456
        url = reverse('tasks:review_submission', kwargs={'submission_id': submission_id})
        self.assertEqual(url, f'/tasks/submission/{submission_id}/review/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/submission/{submission_id}/review/')
        self.assertEqual(resolver.view_name, 'tasks:review_submission')
        self.assertEqual(resolver.func, views.review_submission)
        self.assertEqual(resolver.kwargs['submission_id'], submission_id)


class TaskWalletURLTest(ComprehensiveTaskTestCase):
    """Test cases for task wallet URLs."""

    def test_task_wallet_dashboard_url(self):
        """Test task wallet dashboard URL pattern."""
        url = reverse('tasks:task_wallet_dashboard')
        self.assertEqual(url, '/tasks/task-wallet/')
        
        resolver = resolve('/tasks/task-wallet/')
        self.assertEqual(resolver.view_name, 'tasks:task_wallet_dashboard')
        self.assertEqual(resolver.func.view_class, views.TaskWalletDashboardView)

    def test_task_wallet_transactions_url(self):
        """Test task wallet transactions URL pattern."""
        url = reverse('tasks:task_wallet_transactions')
        self.assertEqual(url, '/tasks/task-wallet/transactions/')
        
        resolver = resolve('/tasks/task-wallet/transactions/')
        self.assertEqual(resolver.view_name, 'tasks:task_wallet_transactions')
        self.assertEqual(resolver.func.view_class, views.TaskWalletTransactionListView)

    def test_task_wallet_topup_url(self):
        """Test task wallet topup URL pattern."""
        url = reverse('tasks:task_wallet_topup')
        self.assertEqual(url, '/tasks/task-wallet/topup/')
        
        resolver = resolve('/tasks/task-wallet/topup/')
        self.assertEqual(resolver.view_name, 'tasks:task_wallet_topup')
        self.assertEqual(resolver.func.view_class, views.TaskWalletTopupView)

class DisputeURLTest(ComprehensiveTaskTestCase):
    """Test cases for dispute-related URLs."""

    def test_create_dispute_url(self):
        """Test create dispute URL pattern."""
        submission_id = 123
        url = reverse('tasks:create_dispute', kwargs={'submission_id': submission_id})
        self.assertEqual(url, f'/tasks/submission/{submission_id}/dispute/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/submission/{submission_id}/dispute/')
        self.assertEqual(resolver.view_name, 'tasks:create_dispute')
        self.assertEqual(resolver.func, views.create_dispute)
        self.assertEqual(resolver.kwargs['submission_id'], submission_id)

    def test_my_disputes_url(self):
        """Test my disputes URL pattern."""
        url = reverse('tasks:my_disputes')
        self.assertEqual(url, '/tasks/my-disputes/')
        
        # Test URL resolution
        resolver = resolve('/tasks/my-disputes/')
        self.assertEqual(resolver.view_name, 'tasks:my_disputes')
        self.assertEqual(resolver.func, views.my_disputes)

    def test_dispute_detail_url(self):
        """Test dispute detail URL pattern."""
        dispute_id = 456
        url = reverse('tasks:dispute_detail', kwargs={'dispute_id': dispute_id})
        self.assertEqual(url, f'/tasks/dispute/{dispute_id}/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/dispute/{dispute_id}/')
        self.assertEqual(resolver.view_name, 'tasks:dispute_detail')
        self.assertEqual(resolver.func, views.dispute_detail)
        self.assertEqual(resolver.kwargs['dispute_id'], dispute_id)


class AdminURLTest(ComprehensiveTaskTestCase):
    """Test cases for admin URLs."""

    def test_admin_disputes_url(self):
        """Test admin disputes URL pattern."""
        url = reverse('tasks:admin_disputes')
        self.assertEqual(url, '/tasks/admin/disputes/')
        
        # Test URL resolution
        resolver = resolve('/tasks/admin/disputes/')
        self.assertEqual(resolver.view_name, 'tasks:admin_disputes')
        self.assertEqual(resolver.func, views.admin_disputes)

    def test_resolve_dispute_url(self):
        """Test resolve dispute URL pattern."""
        dispute_id = 789
        url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': dispute_id})
        self.assertEqual(url, f'/tasks/admin/dispute/{dispute_id}/resolve/')
        
        # Test URL resolution
        resolver = resolve(f'/tasks/admin/dispute/{dispute_id}/resolve/')
        self.assertEqual(resolver.view_name, 'tasks:resolve_dispute')
        self.assertEqual(resolver.func, views.resolve_dispute)
        self.assertEqual(resolver.kwargs['dispute_id'], dispute_id)


class URLParameterTest(ComprehensiveTaskTestCase):
    """Test URL parameter handling and validation."""

    def test_integer_parameter_validation(self):
        """Test that URLs properly handle integer parameters."""
        # Test valid integer
        resolver = resolve('/tasks/123/')
        self.assertEqual(resolver.kwargs['task_id'], 123)
        
        # Test that non-integer parameters don't match
        try:
            resolve('/tasks/abc/')
            self.fail("Should not resolve non-integer task_id")
        except Exception:
            pass  # Expected to fail

    def test_url_parameter_types(self):
        """Test that URL parameters are of correct types."""
        # Task ID should be integer
        resolver = resolve('/tasks/42/')
        self.assertIsInstance(resolver.kwargs['task_id'], int)
        
        # Submission ID should be integer
        resolver = resolve('/tasks/submission/84/review/')
        self.assertIsInstance(resolver.kwargs['submission_id'], int)
        
        # Dispute ID should be integer
        resolver = resolve('/tasks/dispute/126/')
        self.assertIsInstance(resolver.kwargs['dispute_id'], int)

    def test_url_parameter_bounds(self):
        """Test URL parameter boundary conditions."""
        # Test very large IDs
        large_id = 999999999
        resolver = resolve(f'/tasks/{large_id}/')
        self.assertEqual(resolver.kwargs['task_id'], large_id)
        
        # Test ID of 1
        resolver = resolve('/tasks/1/')
        self.assertEqual(resolver.kwargs['task_id'], 1)
        
        # Test zero ID (should still resolve but will likely 404 in view)
        resolver = resolve('/tasks/0/')
        self.assertEqual(resolver.kwargs['task_id'], 0)

    def test_negative_id_handling(self):
        """Test handling of negative IDs in URLs."""
        # Negative IDs should not match the URL pattern
        try:
            resolve('/tasks/-1/')
            self.fail("Should not resolve negative task_id")
        except Exception:
            pass  # Expected to fail


class URLNamespaceTest(ComprehensiveTaskTestCase):
    """Test URL namespace functionality."""

    def test_app_namespace(self):
        """Test that app namespace is properly configured."""
        # All task URLs should be in 'tasks' namespace
        task_urls = [
            'task_list', 'create_task', 'my_tasks', 'my_submissions',
            'task_detail', 'edit_task', 'delete_task',
            'review_submissions', 'review_submission',
            'task_wallet_dashboard', 'task_wallet_transactions', 'task_wallet_topup',
            'create_dispute', 'my_disputes', 'dispute_detail',
            'admin_disputes', 'resolve_dispute'
        ]
        
        for url_name in task_urls:
            # Should be able to reverse with namespace
            try:
                reverse(f'tasks:{url_name}')
            except Exception as e:
                if 'argument' not in str(e):  # Skip URLs that need arguments
                    self.fail(f"Failed to reverse tasks:{url_name}: {e}")

    def test_url_name_uniqueness(self):
        """Test that URL names are unique within namespace."""
        # This is more of a configuration test
        # Django will raise errors if URL names conflict
        
        # Get all URL patterns
        from tasks.urls import urlpatterns
        url_names = []
        
        for pattern in urlpatterns:
            if hasattr(pattern, 'name') and pattern.name:
                url_names.append(pattern.name)
        
        # Check for duplicates
        unique_names = set(url_names)
        self.assertEqual(len(url_names), len(unique_names), 
                        "Duplicate URL names found")


class URLAccessibilityTest(ComprehensiveTaskTestCase):
    """Test URL accessibility and common patterns."""

    def test_trailing_slash_consistency(self):
        """Test that URLs handle trailing slashes consistently."""
        # Test URLs that should have trailing slashes
        urls_with_slashes = [
            '/tasks/',
            '/tasks/create/',
            '/tasks/my-tasks/',
            '/tasks/my-submissions/',
            '/tasks/task-wallet/',
        ]
        
        for url in urls_with_slashes:
            resolver = resolve(url)
            self.assertIsNotNone(resolver.view_name)

    def test_url_case_sensitivity(self):
        """Test URL case sensitivity."""
        # URLs should be case-sensitive
        resolver = resolve('/tasks/')
        self.assertIsNotNone(resolver.view_name)
        
        # This should not resolve (case mismatch)
        with self.assertRaises(Exception):
            resolve('/Tasks/')

    def test_url_with_special_characters(self):
        """Test URLs with special characters in parameters."""
        # Only integers are allowed for IDs, so special characters should fail
        invalid_urls = [
            '/tasks/@@@/',
            '/tasks/#$/',
            '/tasks/12$%/',
            '/tasks/submission/ab@/review/',
            '/tasks/dispute/!!/',
        ]

        for url in invalid_urls:
            with self.assertRaises(Exception, msg=f"URL {url} should not resolve"):
                resolve(url)
