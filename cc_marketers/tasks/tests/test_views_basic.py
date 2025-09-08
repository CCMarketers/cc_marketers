# tests/test_views_basic.py
"""
Test suite for basic task views including task listing, detail, and creation.
Tests permissions, subscription requirements, and core functionality.
"""
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from tasks.models import Task, Submission
from wallets.models import EscrowTransaction
from .test_base import ComprehensiveTaskTestCase


class TaskListViewTest(ComprehensiveTaskTestCase):
    """Test cases for task_list view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:task_list')
        
        # Create various tasks for testing
        self.active_task = self.create_task(
            title='Active Task',
            status='active',
            deadline=timezone.now() + timedelta(days=5),
            remaining_slots=3
        )
        
        self.expired_task = self.create_task(
            title='Expired Task',
            deadline=timezone.now() - timedelta(days=1)
        )
        
        self.full_task = self.create_task(
            title='Full Task',
            remaining_slots=0
        )
        
        self.paused_task = self.create_task(
            title='Paused Task',
            status='paused'
        )

    def test_requires_login(self):
        """Test that task list requires login."""
        self.assert_requires_login(self.url)

    def test_displays_only_active_available_tasks(self):
        """Test that only active, non-expired, non-full tasks are shown."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        tasks = response.context['tasks']
        
        # Should only show active task
        task_titles = [task.title for task in tasks]
        self.assertIn('Active Task', task_titles)
        self.assertNotIn('Expired Task', task_titles)
        self.assertNotIn('Full Task', task_titles)
        self.assertNotIn('Paused Task', task_titles)

    # def test_task_progress_calculation(self):
    #     """Test that task progress is correctly calculated."""
    #     # Create task with some filled slots
    #     self.create_task(
    #         title='Progress Task',
    #         total_slots=10,
    #         remaining_slots=7  # 3 filled, 7 remaining
    #     )
        
    #     self.login_user(self.member)
    #     response = self.client.get(self.url)
        
    #     tasks = response.context['tasks']
    #     progress_task = next((t for t in tasks if t.title == 'Progress Task'), None)
    #     self.assertIsNotNone(progress_task)
    #     self.assertEqual(progress_task.progress, 30.0)  # 3/10 * 100

    def test_already_submitted_flag(self):
        """Test that already_submitted flag is set correctly."""
        # Create submission for member
        self.create_submission(task=self.active_task, member=self.member)
        
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        tasks = response.context['tasks']
        active_task_obj = next((t for t in tasks if t.title == 'Active Task'), None)
        self.assertIsNotNone(active_task_obj)
        self.assertTrue(active_task_obj.already_submitted)

    def test_search_filter(self):
        """Test search functionality."""
        self.create_task(title='Python Programming Task')
        self.create_task(title='Data Analysis Task')
        
        self.login_user(self.member)
        
        # Search for 'Python'
        response = self.client.get(self.url, {'search': 'Python'})
        self.assertEqual(response.status_code, 200)
        
        tasks = response.context['tasks']
        task_titles = [task.title for task in tasks]
        self.assertIn('Python Programming Task', task_titles)
        self.assertNotIn('Data Analysis Task', task_titles)

    def test_payout_filters(self):
        """Test minimum and maximum payout filters."""
        self.create_task(title='Low Pay Task', payout_per_slot=Decimal('5.00'))
        self.create_task(title='High Pay Task', payout_per_slot=Decimal('50.00'))
        
        self.login_user(self.member)
        
        # Filter by minimum payout
        response = self.client.get(self.url, {'min_payout': '20.00'})
        tasks = response.context['tasks']
        task_titles = [task.title for task in tasks]
        self.assertIn('High Pay Task', task_titles)
        self.assertNotIn('Low Pay Task', task_titles)
        
        # Filter by maximum payout
        response = self.client.get(self.url, {'max_payout': '10.00'})
        tasks = response.context['tasks']
        task_titles = [task.title for task in tasks]
        self.assertIn('Low Pay Task', task_titles)
        self.assertNotIn('High Pay Task', task_titles)

    def test_pagination(self):
        """Test pagination works correctly."""
        # Create 15 tasks (more than the 10 per page limit)
        for i in range(15):
            self.create_task(title=f'Task {i}')
        
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        tasks = response.context['tasks']
        self.assertEqual(len(tasks), 10)  # First page should have 10 tasks
        
        # Test second page
        response = self.client.get(self.url, {'page': 2})
        tasks = response.context['tasks']
        self.assertGreaterEqual(len(tasks), 5)  # Should have remaining tasks


class TaskDetailViewTest(ComprehensiveTaskTestCase):
    """Test cases for task_detail view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:task_detail', kwargs={'task_id': self.task.id})

    def test_requires_login(self):
        """Test that task detail requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that task detail requires subscription."""
        self.assert_subscription_required(self.url)

    def test_get_task_detail(self):
        """Test GET request to task detail."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/task_detail.html')
        self.assertEqual(response.context['task'], self.task)
        self.assertIsNotNone(response.context['form'])

    def test_advertiser_cannot_view_own_task_for_submission(self):
        """Test that advertisers cannot submit to their own tasks."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertRedirects(response, reverse('tasks:task_list'))
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('cannot submit to your own task' in str(m) for m in messages_list))

    def test_show_existing_submission(self):
        """Test that existing submission is shown."""
        existing_submission = self.create_submission(task=self.task, member=self.member)
        
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.context['existing_submission'], existing_submission)

    def test_post_submission_success(self):
        """Test successful submission creation."""
        self.login_user(self.member)
        
        data = {
            'proof_text': 'I completed the task successfully',
        }
        
        response = self.client.post(self.url, data)
        
        # Should redirect back to task detail
        self.assertRedirects(response, self.url)
        
        # Check submission was created
        submission = Submission.objects.get(task=self.task, member=self.member)
        self.assertEqual(submission.proof_text, 'I completed the task successfully')
        
        # Check remaining slots decreased
        self.task.refresh_from_db()
        self.assertEqual(self.task.remaining_slots, 4)  # Was 5, now 4

    def test_post_submission_with_files(self):
        """Test submission with file uploads."""
        self.login_user(self.member)
        
        proof_file = self.create_test_file('proof.txt', b'proof content')
        screenshot = self.create_test_image('screenshot.jpg')
        
        data = {
            'proof_text': 'Task completed with files',
            'proof_file': proof_file,
            'screenshot': screenshot
        }
        
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, self.url)
        
        submission = Submission.objects.get(task=self.task, member=self.member)
        self.assertEqual(submission.proof_text, 'Task completed with files')
        self.assertTrue(submission.proof_file)
        self.assertTrue(submission.screenshot)

    def test_cannot_submit_twice(self):
        """Test that user cannot submit twice to same task."""
        # Create existing submission
        self.create_submission(task=self.task, member=self.member)
        
        self.login_user(self.member)
        
        data = {'proof_text': 'Second submission attempt'}
        self.client.post(self.url, data)
        
        # Should not create second submission
        self.assertEqual(Submission.objects.filter(task=self.task, member=self.member).count(), 1)

    def test_cannot_submit_to_full_task(self):
        """Test cannot submit to full task."""
        # Make task full
        self.task.remaining_slots = 0
        self.task.save()
        
        self.login_user(self.member)
        
        data = {'proof_text': 'Submission to full task'}
        self.client.post(self.url, data)
        
        # Should not create submission
        self.assertFalse(Submission.objects.filter(task=self.task, member=self.member).exists())

    def test_cannot_submit_to_expired_task(self):
        """Test cannot submit to expired task."""
        # Make task expired
        self.task.deadline = timezone.now() - timedelta(hours=1)
        self.task.save()
        
        self.login_user(self.member)
        
        data = {'proof_text': 'Submission to expired task'}
        self.client.post(self.url, data)
        
        # Should not create submission
        self.assertFalse(Submission.objects.filter(task=self.task, member=self.member).exists())

    def test_invalid_form_submission(self):
        """Test submission with invalid form data."""
        self.login_user(self.member)
        
        # Submit empty form (proof_text is required based on form)
        data = {}
        response = self.client.post(self.url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/task_detail.html')

    def test_nonexistent_task_404(self):
        """Test that accessing nonexistent task returns 404."""
        url = reverse('tasks:task_detail', kwargs={'task_id': 99999})
        self.login_user(self.member)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class CreateTaskViewTest(ComprehensiveTaskTestCase):
    """Test cases for create_task view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:create_task')

    def test_requires_login(self):
        """Test that create task requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that create task requires subscription."""
        self.assert_subscription_required(self.url)

    def test_requires_advertiser_role(self):
        """Test that only advertisers can create tasks."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertRedirects(response, reverse('tasks:task_list'))
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('Only advertisers can create tasks' in str(m) for m in messages_list))

    def test_staff_can_create_tasks(self):
        """Test that staff members can create tasks regardless of role."""
        self.login_user(self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/create_task.html')

    def test_get_create_task_form(self):
        """Test GET request shows create task form."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/create_task.html')
        self.assertIsNotNone(response.context['form'])

    def test_successful_task_creation(self):
        """Test successful task creation with escrow."""
        self.login_user(self.advertiser)
        
        future_date = timezone.now() + timedelta(days=7)
        data = {
            'title': 'New Test Task',
            'description': 'This is a test task description',
            'payout_per_slot': '15.00',
            'total_slots': '3',
            'deadline': future_date.strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Provide screenshot and description'
        }
        
        response = self.client.post(self.url, data)
        
        # Should redirect to my_tasks
        self.assertRedirects(response, reverse('tasks:my_tasks'))
        
        # Check task was created
        task = Task.objects.get(title='New Test Task')
        self.assertEqual(task.advertiser, self.advertiser)
        self.assertEqual(task.payout_per_slot, Decimal('15.00'))
        self.assertEqual(task.total_slots, 3)
        self.assertEqual(task.remaining_slots, 3)
        
        # Check escrow was created
        escrow = EscrowTransaction.objects.get(task=task)
        self.assertEqual(escrow.amount, Decimal('45.00'))  # 15.00 * 3
        self.assertEqual(escrow.status, 'locked')

    def test_insufficient_balance_handling(self):
        """Test handling of insufficient task wallet balance."""
        # Set task wallet balance to insufficient amount
        self.advertiser_task_wallet.balance = Decimal('10.00')
        self.advertiser_task_wallet.save()
        
        self.login_user(self.advertiser)
        
        data = {
            'title': 'Expensive Task',
            'description': 'This task costs more than available balance',
            'payout_per_slot': '50.00',
            'total_slots': '5',  # Total: $250, but only $10 available
            'deadline': (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Provide proof'
        }
        
        response = self.client.post(self.url, data)
        
        # Should redirect to topup page
        self.assertRedirects(response, reverse('tasks:task_wallet_topup'))
        
        # Check task was not created
        self.assertFalse(Task.objects.filter(title='Expensive Task').exists())

    def test_form_validation_errors(self):
        """Test form validation with invalid data."""
        self.login_user(self.advertiser)
        
        # Invalid data - missing required fields
        data = {
            'title': '',  # Required
            'payout_per_slot': '0.00',  # Below minimum
            'total_slots': '0'  # Below minimum
        }
        
        response = self.client.post(self.url, data)
        
        # Should stay on form page with errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/create_task.html')
        form = response.context['form']
        self.assertTrue(form.errors)

    def test_deadline_in_past(self):
        """Test that past deadline is rejected."""
        self.login_user(self.advertiser)
        
        past_date = timezone.now() - timedelta(days=1)
        data = {
            'title': 'Past Task',
            'description': 'Task with past deadline',
            'payout_per_slot': '10.00',
            'total_slots': '2',
            'deadline': past_date.strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Provide proof'
        }
        
        response = self.client.post(self.url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/create_task.html')


class MyTasksViewTest(ComprehensiveTaskTestCase):
    """Test cases for my_tasks view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:my_tasks')
        
        # Create tasks for the advertiser
        self.my_task = self.create_task(
            advertiser=self.advertiser,
            title='My Task'
        )
        
        # Create tasks for another user
        another_advertiser = self.create_user('another_advertiser', 'another@test.com', role='advertiser')
        self.other_task = self.create_task(
            advertiser=another_advertiser,
            title='Other Task'
        )

    def test_requires_login(self):
        """Test that my tasks requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that my tasks requires subscription."""
        self.assert_subscription_required(self.url)

    def test_shows_only_user_tasks(self):
        """Test that only current user's tasks are shown."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/my_tasks.html')
        
        tasks = response.context['tasks']
        task_titles = [task.title for task in tasks]
        self.assertIn('My Task', task_titles)
        self.assertNotIn('Other Task', task_titles)

    def test_task_statistics_annotation(self):
        """Test that tasks are annotated with submission statistics."""
        # Create submissions with different statuses
        member1 = self.create_user('member1', 'member1@test.com')
        member2 = self.create_user('member2', 'member2@test.com')
        member3 = self.create_user('member3', 'member3@test.com')
        
        self.create_submission(task=self.my_task, member=member1, status='pending')
        self.create_submission(task=self.my_task, member=member2, status='approved')
        self.create_submission(task=self.my_task, member=member3, status='rejected')
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        tasks = response.context['tasks']
        my_task_obj = next((t for t in tasks if t.title == 'My Task'), None)
        
        self.assertIsNotNone(my_task_obj)
        self.assertEqual(my_task_obj.pending_count, 1)
        self.assertEqual(my_task_obj.approved_count, 1)
        self.assertEqual(my_task_obj.rejected_count, 1)
        self.assertEqual(my_task_obj.submissions_count, 3)

    def test_pagination_works(self):
        """Test pagination for my tasks."""
        # Create many tasks
        for i in range(15):
            self.create_task(
                advertiser=self.advertiser,
                title=f'Task {i}'
            )
        
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        tasks = response.context['tasks']
        self.assertEqual(len(tasks), 10)  # Should show 10 per page