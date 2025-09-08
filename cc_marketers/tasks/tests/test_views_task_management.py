# tests/test_views_task_management.py
"""
Test suite for task management views including edit, delete, and submission management.
"""
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from tasks.models import Task
from wallets.models import EscrowTransaction
from .test_base import ComprehensiveTaskTestCase


class EditTaskViewTest(ComprehensiveTaskTestCase):
    """Test cases for edit_task view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:edit_task', kwargs={'task_id': self.task.id})

    def test_requires_login(self):
        """Test that edit task requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that edit task requires subscription."""
        self.assert_subscription_required(self.url)

    def test_only_owner_can_edit(self):
        """Test that only task owner can edit task."""
        another_advertiser = self.create_user('another', 'another@test.com', role='advertiser', is_subscribed=True)
        self.login_user(another_advertiser)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_with_submissions(self):
        """Test that task cannot be edited if it has submissions."""
        # Create a submission
        self.create_submission(task=self.task, member=self.member)
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertRedirects(response, reverse('tasks:my_tasks'))
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('cannot edit this task because it already has submissions' in str(m) for m in messages_list))

    def test_get_edit_form(self):
        """Test GET request shows edit form with current data."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/edit_task.html')
        
        form = response.context['form']
        self.assertEqual(form.instance, self.task)
        self.assertEqual(response.context['task'], self.task)

    def test_successful_edit(self):
        """Test successful task editing."""
        self.login_user(self.advertiser)
        
        new_deadline = timezone.now() + timedelta(days=10)
        data = {
            'title': 'Updated Task Title',
            'description': 'Updated description',
            'payout_per_slot': str(self.task.payout_per_slot),
            'total_slots': str(self.task.total_slots),
            'deadline': new_deadline.strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Updated instructions'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:my_tasks'))
        
        # Check task was updated
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, 'Updated Task Title')
        self.assertEqual(self.task.description, 'Updated description')
        self.assertEqual(self.task.proof_instructions, 'Updated instructions')

    def test_form_validation_on_edit(self):
        """Test form validation when editing."""
        self.login_user(self.advertiser)
        
        data = {
            'title': '',  # Invalid - required
            'description': 'Description',
            'payout_per_slot': '0.00',  # Invalid - below minimum
            'total_slots': '0',  # Invalid - below minimum
            'deadline': (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Instructions'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/edit_task.html')
        form = response.context['form']
        self.assertTrue(form.errors)

    def test_nonexistent_task_404(self):
        """Test editing nonexistent task returns 404."""
        url = reverse('tasks:edit_task', kwargs={'task_id': 99999})
        self.login_user(self.advertiser)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class DeleteTaskViewTest(ComprehensiveTaskTestCase):
    """Test cases for delete_task view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:delete_task', kwargs={'task_id': self.task.id})

    def test_requires_login(self):
        """Test that delete task requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that delete task requires subscription."""
        self.assert_subscription_required(self.url)

    def test_only_owner_can_delete(self):
        """Test that only task owner can delete task."""
        another_advertiser = self.create_user('another', 'another@test.com', role='advertiser', is_subscribed=True)
        self.login_user(another_advertiser)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_with_submissions(self):
        """Test that task cannot be deleted if it has submissions."""
        # Create a submission
        self.create_submission(task=self.task, member=self.member)
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertRedirects(response, reverse('tasks:my_tasks'))
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('cannot delete this task because it already has submissions' in str(m) for m in messages_list))

    def test_get_delete_confirmation(self):
        """Test GET request shows delete confirmation."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/confirm_delete.html')
        self.assertEqual(response.context['task'], self.task)

    def test_successful_delete_with_escrow_refund(self):
        """Test successful task deletion refunds escrow."""
        # Ensure escrow exists
        self.assertTrue(EscrowTransaction.objects.filter(task=self.task, status='locked').exists())
        
        # Get initial balance
        initial_balance = self.advertiser_task_wallet.balance
        
        self.login_user(self.advertiser)
        response = self.client.post(self.url)
        
        self.assertRedirects(response, reverse('tasks:my_tasks'))
        
        # Check task was deleted
        self.assertFalse(Task.objects.filter(id=self.task.id).exists())
        
        # Check escrow was refunded
        self.advertiser_task_wallet.refresh_from_db()
        # Balance should be restored (initial + escrow amount)
        expected_balance = initial_balance + self.escrow.amount
        self.assertEqual(self.advertiser_task_wallet.balance, expected_balance)

    def test_delete_without_escrow(self):
        """Test deleting task that has no locked escrow."""
        # Delete existing escrow
        self.escrow.delete()
        
        self.login_user(self.advertiser)
        response = self.client.post(self.url)
        
        self.assertRedirects(response, reverse('tasks:my_tasks'))
        
        # Task should still be deleted successfully
        self.assertFalse(Task.objects.filter(id=self.task.id).exists())

    def test_nonexistent_task_404(self):
        """Test deleting nonexistent task returns 404."""
        url = reverse('tasks:delete_task', kwargs={'task_id': 99999})
        self.login_user(self.advertiser)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class MySubmissionsViewTest(ComprehensiveTaskTestCase):
    """Test cases for my_submissions view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:my_submissions')
        
        # Create submissions for the member
        self.my_submission = self.create_submission(
            task=self.task,
            member=self.member,
            status='approved'
        )
        
        # Create submission for another user
        another_member = self.create_user('another_member', 'another@test.com')
        self.other_submission = self.create_submission(
            task=self.create_task(title='Another Task'),
            member=another_member,
            status='pending'
        )

    def test_requires_login(self):
        """Test that my submissions requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that my submissions requires subscription."""
        self.assert_subscription_required(self.url)

    def test_shows_only_user_submissions(self):
        """Test that only current user's submissions are shown."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/my_submissions.html')
        
        submissions = response.context['submissions']
        submission_ids = [s.id for s in submissions]
        self.assertIn(self.my_submission.id, submission_ids)
        self.assertNotIn(self.other_submission.id, submission_ids)

    def test_submissions_ordered_by_review_date(self):
        """Test that submissions are ordered by review date."""
        # Create multiple submissions
        submission1 = self.create_submission(
            task=self.create_task(title='Task 1'),
            member=self.member,
            status='approved'
        )
        submission1.reviewed_at = timezone.now() - timedelta(hours=2)
        submission1.save()
        
        submission2 = self.create_submission(
            task=self.create_task(title='Task 2'),
            member=self.member,
            status='rejected'
        )
        submission2.reviewed_at = timezone.now() - timedelta(hours=1)
        submission2.save()
        
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        submissions = list(response.context['submissions'])
        # Most recently reviewed should come first
        self.assertEqual(submissions[0], submission2)

    def test_pagination_works(self):
        """Test pagination for my submissions."""
        # Create many submissions
        for i in range(15):
            task = self.create_task(title=f'Task {i}')
            member = self.create_user(f'member{i}', f'member{i}@test.com')
            # Create submission for another member first to avoid unique constraint
            self.create_submission(task=task, member=member)
            # Now create for our test member
            self.create_submission(
                task=self.create_task(title=f'My Task {i}'),
                member=self.member
            )
        
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        submissions = response.context['submissions']
        self.assertEqual(len(submissions), 10)  # Should show 10 per page


class ReviewSubmissionsViewTest(ComprehensiveTaskTestCase):
    """Test cases for review_submissions view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:review_submissions', kwargs={'task_id': self.task.id})
        
        # Create submissions with different statuses
        member1 = self.create_user('member1', 'member1@test.com')
        member2 = self.create_user('member2', 'member2@test.com')
        member3 = self.create_user('member3', 'member3@test.com')
        
        self.pending_submission = self.create_submission(
            task=self.task, member=member1, status='pending'
        )
        self.approved_submission = self.create_submission(
            task=self.task, member=member2, status='approved'
        )
        self.rejected_submission = self.create_submission(
            task=self.task, member=member3, status='rejected'
        )

    def test_requires_login(self):
        """Test that review submissions requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that review submissions requires subscription."""
        self.assert_subscription_required(self.url)

    def test_only_owner_can_review(self):
        """Test that only task owner can review submissions."""
        another_advertiser = self.create_user('another', 'another@test.com', role='advertiser', is_subscribed=True)
        self.login_user(another_advertiser)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_shows_only_pending_submissions(self):
        """Test that only pending submissions are shown for review."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/review_submissions.html')
        
        submissions = response.context['submissions']
        submission_ids = [s.id for s in submissions]
        
        self.assertIn(self.pending_submission.id, submission_ids)
        self.assertNotIn(self.approved_submission.id, submission_ids)
        self.assertNotIn(self.rejected_submission.id, submission_ids)

    def test_shows_submission_counts(self):
        """Test that submission counts are shown correctly."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.context['approved_count'], 1)
        self.assertEqual(response.context['rejected_count'], 1)

    def test_nonexistent_task_404(self):
        """Test reviewing submissions for nonexistent task returns 404."""
        url = reverse('tasks:review_submissions', kwargs={'task_id': 99999})
        self.login_user(self.advertiser)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class ReviewSubmissionViewTest(ComprehensiveTaskTestCase):
    """Test cases for review_submission view."""
    
    def setUp(self):
        super().setUp()
        self.submission = self.create_submission(
            task=self.task,
            member=self.member,
            status='pending'
        )
        self.url = reverse('tasks:review_submission', kwargs={'submission_id': self.submission.id})

    def test_requires_login(self):
        """Test that review submission requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that review submission requires subscription."""
        self.assert_subscription_required(self.url)

    def test_only_owner_or_staff_can_review(self):
        """Test that only task owner or staff can review submission."""
        another_user = self.create_user('another', 'another@test.com', is_subscribed=True)
        self.login_user(another_user)
        
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('tasks:task_list'))
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('Permission denied' in str(m) for m in messages_list))

    def test_staff_can_review_any_submission(self):
        """Test that staff can review any submission."""
        self.login_user(self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/review_submission.html')

    def test_get_review_form(self):
        """Test GET request shows review form."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/review_submission.html')
        self.assertEqual(response.context['submission'], self.submission)
        self.assertIsNotNone(response.context['form'])

    def test_approve_submission_releases_escrow(self):
        """Test that approving submission releases escrow to member."""
        initial_member_balance = self.member_wallet.balance
        
        self.login_user(self.advertiser)
        
        data = {
            'decision': 'approve'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:review_submissions', kwargs={'task_id': self.task.id}))
        
        # Check submission was approved
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, 'approved')
        self.assertEqual(self.submission.reviewed_by, self.advertiser)
        self.assertIsNotNone(self.submission.reviewed_at)
        
        # Check escrow was released
        self.escrow.refresh_from_db()
        self.assertEqual(self.escrow.status, 'released')
        
        # Check member received payment (minus company cut)
        self.member_wallet.refresh_from_db()
        expected_payment = self.escrow.amount * Decimal('0.8')  # 80% to member, 20% to company
        self.assertEqual(self.member_wallet.balance, initial_member_balance + expected_payment)

    def test_reject_submission_requires_reason(self):
        """Test that rejecting submission requires a reason."""
        self.login_user(self.advertiser)
        
        data = {
            'decision': 'reject'
            # No rejection_reason provided
        }
        
        response = self.client.post(self.url, data)
        
        # Should show error message and not process rejection
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('Rejection reason is required' in str(m) for m in messages_list))
        
        # Submission should still be pending
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, 'pending')

    def test_reject_submission_with_reason(self):
        """Test successful submission rejection."""
        self.login_user(self.advertiser)
        
        data = {
            'decision': 'reject',
            'rejection_reason': 'Work does not meet requirements'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:review_submissions', kwargs={'task_id': self.task.id}))
        
        # Check submission was rejected
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, 'rejected')
        self.assertEqual(self.submission.rejection_reason, 'Work does not meet requirements')
        self.assertEqual(self.submission.reviewed_by, self.advertiser)
        self.assertIsNotNone(self.submission.reviewed_at)

    def test_invalid_decision(self):
        """Test handling of invalid review decision."""
        self.login_user(self.advertiser)
        
        data = {
            'decision': 'invalid_choice'
        }
        
        response = self.client.post(self.url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/review_submission.html')
        form = response.context['form']
        self.assertTrue(form.errors)

    def test_nonexistent_submission_404(self):
        """Test reviewing nonexistent submission returns 404."""
        url = reverse('tasks:review_submission', kwargs={'submission_id': 99999})
        self.login_user(self.advertiser)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)