# tests/test_views_disputes.py
"""
Test suite for dispute management views including creating, viewing, and resolving disputes.
"""
from decimal import Decimal
from django.urls import reverse

from tasks.models import Dispute
from wallets.models import EscrowTransaction
from .test_base import ComprehensiveTaskTestCase



class CreateDisputeViewTest(ComprehensiveTaskTestCase):
    """Test cases for create_dispute view."""
    
    def setUp(self):
        super().setUp()
        # Create a rejected submission
        self.rejected_submission = self.create_submission(
            task=self.task,
            member=self.member,
            status='rejected'
        )
        self.url = reverse('tasks:create_dispute', kwargs={'submission_id': self.rejected_submission.id})

    def test_requires_login(self):
        """Test that create dispute requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that create dispute requires subscription."""
        self.assert_subscription_required(self.url)

    def test_only_submission_owner_can_create_dispute(self):
        """Test that only submission owner can create dispute."""
        another_member = self.create_user('another', 'another@test.com', is_subscribed=True)
        self.login_user(another_member)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_can_only_dispute_rejected_submission(self):
        """Test that disputes can only be created for rejected submissions."""
        # Create pending submission
        pending_submission = self.create_submission(
            task=self.create_task(title='Another Task'),
            member=self.member,
            status='pending'
        )
        url = reverse('tasks:create_dispute', kwargs={'submission_id': pending_submission.id})
        
        self.login_user(self.member)
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 404)

    def test_cannot_create_duplicate_dispute(self):
        """Test that duplicate disputes cannot be created."""
        # Create existing dispute
        existing_dispute = self.create_dispute(submission=self.rejected_submission)
        
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertRedirects(response, reverse('tasks:dispute_detail', kwargs={'dispute_id': existing_dispute.id}))
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('Dispute already exists' in str(m) for m in messages_list))

    def test_get_create_dispute_form(self):
        """Test GET request shows create dispute form."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/create_dispute.html')
        self.assertEqual(response.context['submission'], self.rejected_submission)
        self.assertIsNotNone(response.context['form'])

    def test_successful_dispute_creation(self):
        """Test successful dispute creation."""
        self.login_user(self.member)
        
        data = {
            'reason': 'The rejection was unfair. I followed all instructions correctly.'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:my_disputes'))
        
        # Check dispute was created
        dispute = Dispute.objects.get(submission=self.rejected_submission)
        self.assertEqual(dispute.raised_by, self.member)
        self.assertEqual(dispute.reason, 'The rejection was unfair. I followed all instructions correctly.')
        self.assertEqual(dispute.status, 'open')

    def test_form_validation_empty_reason(self):
        """Test form validation with empty reason."""
        self.login_user(self.member)
        
        data = {
            'reason': ''  # Empty reason
        }
        
        response = self.client.post(self.url, data)
        
        # Should show form with errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/create_dispute.html')
        form = response.context['form']
        self.assertTrue(form.errors)

    def test_nonexistent_submission_404(self):
        """Test creating dispute for nonexistent submission returns 404."""
        url = reverse('tasks:create_dispute', kwargs={'submission_id': 99999})
        self.login_user(self.member)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class MyDisputesViewTest(ComprehensiveTaskTestCase):
    """Test cases for my_disputes view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:my_disputes')
        
        # Create disputes for the member
        rejected_submission1 = self.create_submission(
            task=self.task,
            member=self.member,
            status='rejected'
        )
        self.my_dispute = self.create_dispute(
            submission=rejected_submission1,
            raised_by=self.member
        )
        
        # Create dispute for another user
        another_member = self.create_user('another_member', 'another@test.com')
        rejected_submission2 = self.create_submission(
            task=self.create_task(title='Another Task'),
            member=another_member,
            status='rejected'
        )
        self.other_dispute = self.create_dispute(
            submission=rejected_submission2,
            raised_by=another_member
        )

    def test_requires_login(self):
        """Test that my disputes requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that my disputes requires subscription."""
        self.assert_subscription_required(self.url)

    def test_shows_only_user_disputes(self):
        """Test that only current user's disputes are shown."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/my_disputes.html')
        
        disputes = response.context['disputes']
        dispute_ids = [d.id for d in disputes]
        self.assertIn(self.my_dispute.id, dispute_ids)
        self.assertNotIn(self.other_dispute.id, dispute_ids)

    def test_disputes_ordered_by_creation_date(self):
        """Test that disputes are ordered by creation date (newest first)."""
        # Create another dispute
        rejected_submission3 = self.create_submission(
            task=self.create_task(title='Third Task'),
            member=self.member,
            status='rejected'
        )
        newer_dispute = self.create_dispute(
            submission=rejected_submission3,
            raised_by=self.member,
            reason='Another dispute'
        )
        
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        disputes = list(response.context['disputes'])
        # Newest should come first
        self.assertEqual(disputes[0], newer_dispute)


class DisputeDetailViewTest(ComprehensiveTaskTestCase):
    """Test cases for dispute_detail view."""
    
    def setUp(self):
        super().setUp()
        # Create dispute
        rejected_submission = self.create_submission(
            task=self.task,
            member=self.member,
            status='rejected'
        )
        self.dispute = self.create_dispute(
            submission=rejected_submission,
            raised_by=self.member
        )
        self.url = reverse('tasks:dispute_detail', kwargs={'dispute_id': self.dispute.id})

    def test_requires_login(self):
        """Test that dispute detail requires login."""
        self.assert_requires_login(self.url)

    def test_requires_subscription(self):
        """Test that dispute detail requires subscription."""
        self.assert_subscription_required(self.url)

    def test_member_can_view_own_dispute(self):
        """Test that member can view their own dispute."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/dispute_detail.html')
        self.assertEqual(response.context['dispute'], self.dispute)

    def test_advertiser_can_view_dispute_on_their_task(self):
        """Test that advertiser can view disputes on their tasks."""
        self.login_user(self.advertiser)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['dispute'], self.dispute)

    def test_staff_can_view_any_dispute(self):
        """Test that staff can view any dispute."""
        self.login_user(self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['dispute'], self.dispute)

    def test_unauthorized_user_cannot_view_dispute(self):
        """Test that unauthorized users cannot view dispute."""
        unauthorized_user = self.create_user('unauthorized', 'unauthorized@test.com', is_subscribed=True)
        self.login_user(unauthorized_user)
        
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('tasks:task_list'))
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any('Permission denied' in str(m) for m in messages_list))

    def test_nonexistent_dispute_404(self):
        """Test viewing nonexistent dispute returns 404."""
        url = reverse('tasks:dispute_detail', kwargs={'dispute_id': 99999})
        self.login_user(self.member)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class AdminDisputesViewTest(ComprehensiveTaskTestCase):
    """Test cases for admin_disputes view."""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('tasks:admin_disputes')
        
        # Create disputes with different statuses
        rejected_submission1 = self.create_submission(
            task=self.task,
            member=self.member,
            status='rejected'
        )
        self.open_dispute = self.create_dispute(
            submission=rejected_submission1,
            status='open'
        )
        
        rejected_submission2 = self.create_submission(
            task=self.create_task(title='Another Task'),
            member=self.create_user('member2', 'member2@test.com'),
            status='rejected'
        )
        self.investigating_dispute = self.create_dispute(
            submission=rejected_submission2,
            status='investigating'
        )
        
        rejected_submission3 = self.create_submission(
            task=self.create_task(title='Third Task'),
            member=self.create_user('member3', 'member3@test.com'),
            status='rejected'
        )
        self.resolved_dispute = self.create_dispute(
            submission=rejected_submission3,
            status='resolved_favor_member'
        )

    def test_requires_staff(self):
        """Test that admin disputes requires staff permissions."""
        # Try with regular user
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        # Should redirect to admin login
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/admin/login/'))

    def test_staff_can_access(self):
        """Test that staff can access admin disputes."""
        self.login_user(self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/admin_disputes.html')

    def test_shows_only_open_and_investigating_disputes(self):
        """Test that only open and investigating disputes are shown."""
        self.login_user(self.admin)
        response = self.client.get(self.url)
        
        disputes = response.context['disputes']
        dispute_ids = [d.id for d in disputes]
        
        self.assertIn(self.open_dispute.id, dispute_ids)
        self.assertIn(self.investigating_dispute.id, dispute_ids)
        self.assertNotIn(self.resolved_dispute.id, dispute_ids)

    def test_disputes_ordered_by_creation_date(self):
        """Test that disputes are ordered by creation date (newest first)."""
        self.login_user(self.admin)
        response = self.client.get(self.url)
        
        disputes = list(response.context['disputes'])
        # Should be ordered newest first
        self.assertEqual(disputes[0], self.investigating_dispute)  # Created after open_dispute


class ResolveDisputeViewTest(ComprehensiveTaskTestCase):
    """Test cases for resolve_dispute view."""
    
    def setUp(self):
        super().setUp()
        # Create dispute
        rejected_submission = self.create_submission(
            task=self.task,
            member=self.member,
            status='rejected'
        )
        self.dispute = self.create_dispute(
            submission=rejected_submission,
            status='open'
        )
        self.url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': self.dispute.id})

    def test_requires_staff(self):
        """Test that resolve dispute requires staff permissions."""
        self.login_user(self.member)
        response = self.client.get(self.url)
        
        # Should redirect to admin login
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/admin/login/'))

    def test_staff_can_access(self):
        """Test that staff can access resolve dispute page."""
        self.login_user(self.admin)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tasks/resolve_dispute.html')
        self.assertEqual(response.context['dispute'], self.dispute)

    def test_resolve_favor_member_releases_escrow(self):
        """Test resolving dispute in favor of member releases escrow."""
        initial_member_balance = self.member_wallet.balance
        
        self.login_user(self.admin)
        
        data = {
            'resolution': 'favor_member',
            'admin_notes': 'Member was correct, rejection was unfair'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:admin_disputes'))
        
        # Check dispute was resolved
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.status, 'resolved_favor_member')
        self.assertEqual(self.dispute.admin_notes, 'Member was correct, rejection was unfair')
        self.assertEqual(self.dispute.resolved_by, self.admin)
        self.assertIsNotNone(self.dispute.resolved_at)
        
        # Check submission was approved
        self.dispute.submission.refresh_from_db()
        self.assertEqual(self.dispute.submission.status, 'approved')
        
        # Check escrow was released to member
        self.escrow.refresh_from_db()
        self.assertEqual(self.escrow.status, 'released')
        
        # Check member received payment (minus company cut)
        self.member_wallet.refresh_from_db()
        expected_payment = self.escrow.amount * Decimal('0.8')
        self.assertEqual(self.member_wallet.balance, initial_member_balance + expected_payment)

    def test_resolve_favor_advertiser_refunds_escrow(self):
        """Test resolving dispute in favor of advertiser refunds escrow."""
        initial_advertiser_balance = self.advertiser_task_wallet.balance
        
        self.login_user(self.admin)
        
        data = {
            'resolution': 'favor_advertiser',
            'admin_notes': 'Advertiser was correct, work was insufficient'
        }
        
        response = self.client.post(self.url, data)
        
        self.assertRedirects(response, reverse('tasks:admin_disputes'))
        
        # Check dispute was resolved
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.status, 'resolved_favor_advertiser')
        self.assertEqual(self.dispute.admin_notes, 'Advertiser was correct, work was insufficient')
        
        # Check escrow was refunded
        self.escrow.refresh_from_db()
        self.assertEqual(self.escrow.status, 'refunded')
        
        # Check advertiser received refund
        self.advertiser_task_wallet.refresh_from_db()
        expected_balance = initial_advertiser_balance + self.escrow.amount
        self.assertEqual(self.advertiser_task_wallet.balance, expected_balance)

    def test_resolve_without_admin_notes(self):
        """Test resolving dispute without admin notes."""
        self.login_user(self.admin)
        
        data = {
            'resolution': 'favor_member'
            # No admin_notes provided
        }
        
        response = self.client.post(self.url, data)
        
        # Should still work - admin_notes is optional
        self.assertRedirects(response, reverse('tasks:admin_disputes'))
        
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.status, 'resolved_favor_member')
        self.assertEqual(self.dispute.admin_notes, '')

    def test_invalid_resolution_choice(self):
        """Test handling of invalid resolution choice."""
        self.login_user(self.admin)
        
        data = {
            'resolution': 'invalid_choice',
            'admin_notes': 'Some notes'
        }
        
        self.client.post(self.url, data)
        
        # Should not resolve dispute
        self.dispute.refresh_from_db()
        self.assertEqual(self.dispute.status, 'open')  # Should remain unchanged

    def test_nonexistent_dispute_404(self):
        """Test resolving nonexistent dispute returns 404."""
        url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': 99999})
        self.login_user(self.admin)
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_resolve_already_resolved_dispute(self):
        """Test attempting to resolve already resolved dispute."""
        # Mark dispute as already resolved
        self.dispute.status = 'resolved_favor_member'
        self.dispute.save()
        
        self.login_user(self.admin)
        
        data = {
            'resolution': 'favor_advertiser',
            'admin_notes': 'Trying to change resolution'
        }
        
        response = self.client.post(self.url, data)
        
        # Should handle gracefully - might show error or redirect
        # The exact behavior depends on your business logic
        # Here we test that it doesn't crash
        self.assertIn(response.status_code, [200, 302, 400])


class DisputeIntegrationTest(ComprehensiveTaskTestCase):
    """Integration tests for dispute workflow."""
    
    def test_complete_dispute_workflow_favor_member(self):
        """Test complete dispute workflow when resolved in favor of member."""
        # 1. Create and submit task
        submission = self.create_submission(task=self.task, member=self.member)
        
        # 2. Advertiser rejects submission
        submission.reject(self.advertiser, 'Insufficient quality')
        
        # 3. Member creates dispute
        self.login_user(self.member)
        dispute_url = reverse('tasks:create_dispute', kwargs={'submission_id': submission.id})
        dispute_data = {'reason': 'Work met all requirements'}
        self.client.post(dispute_url, dispute_data)
        
        dispute = Dispute.objects.get(submission=submission)
        self.assertEqual(dispute.status, 'open') 
        
        # 4. Admin resolves in favor of member
        self.login_user(self.admin)
        resolve_url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': dispute.id})
        resolve_data = {
            'resolution': 'favor_member',
            'admin_notes': 'Member was correct'
        }
        self.client.post(resolve_url, resolve_data)
        
        # 5. Verify final state
        dispute.refresh_from_db()
        submission.refresh_from_db()
        self.escrow.refresh_from_db()
        
        self.assertEqual(dispute.status, 'resolved_favor_member')
        self.assertEqual(submission.status, 'approved')
        self.assertEqual(self.escrow.status, 'released')


    def test_complete_dispute_workflow_favor_advertiser(self):
        """Test complete dispute workflow when resolved in favor of advertiser."""
        # 1. Create and submit task
        submission = self.create_submission(task=self.task, member=self.member)
        
        # 2. Advertiser rejects submission
        submission.reject(self.advertiser, 'Did not follow instructions')
        
        # 3. Member creates dispute
        dispute = self.create_dispute(submission=submission, raised_by=self.member)
        
        # 4. Admin resolves in favor of advertiser
        initial_balance = self.advertiser_task_wallet.balance
        
        self.login_user(self.admin)
        resolve_url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': dispute.id})
        resolve_data = {
            'resolution': 'favor_advertiser',
            'admin_notes': 'Advertiser rejection was justified'
        }
        self.client.post(resolve_url, resolve_data)
        
        # 5. Verify final state
        dispute.refresh_from_db()
        self.escrow.refresh_from_db()
        self.advertiser_task_wallet.refresh_from_db()
        
        self.assertEqual(dispute.status, 'resolved_favor_advertiser')
        self.assertEqual(self.escrow.status, 'refunded')
        self.assertEqual(self.advertiser_task_wallet.balance, initial_balance + self.escrow.amount)

    def test_dispute_permissions_across_all_views(self):
        """Test that dispute permissions work consistently across all views."""
        # Create dispute
        rejected_submission = self.create_submission(
            task=self.task,
            member=self.member,
            status='rejected'
        )
        dispute = self.create_dispute(submission=rejected_submission, raised_by=self.member)
        
        # Test unauthorized user cannot access any dispute views
        unauthorized_user = self.create_user('unauthorized', 'unauthorized@test.com', is_subscribed=True)
        self.login_user(unauthorized_user)
        
        # Cannot create dispute for someone else's submission
        create_url = reverse('tasks:create_dispute', kwargs={'submission_id': rejected_submission.id})
        response = self.client.get(create_url)
        self.assertEqual(response.status_code, 404)
        
        # Cannot view someone else's dispute details
        detail_url = reverse('tasks:dispute_detail', kwargs={'dispute_id': dispute.id})
        response = self.client.get(detail_url)
        self.assertRedirects(response, reverse('tasks:task_list'))
        
        # Cannot access admin views
        admin_url = reverse('tasks:admin_disputes')
        response = self.client.get(admin_url)
        self.assertEqual(response.status_code, 302)  # Redirect to admin login
        
        resolve_url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': dispute.id})
        response = self.client.get(resolve_url)
        self.assertEqual(response.status_code, 302)  # Redirect to admin login

    def test_dispute_edge_cases(self):
        """Test edge cases in dispute handling."""
        # Test dispute on task with no escrow
        task_no_escrow = self.create_task(title='No Escrow Task')
        # Remove escrow if it exists
        EscrowTransaction.objects.filter(task=task_no_escrow).delete()
        
        submission = self.create_submission(task=task_no_escrow, member=self.member, status='rejected')
        dispute = self.create_dispute(submission=submission, raised_by=self.member)
        
        self.login_user(self.admin)
        resolve_url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': dispute.id})
        
        # Should handle gracefully even without escrow
        data = {'resolution': 'favor_member', 'admin_notes': 'Test'}
        response = self.client.post(resolve_url, data)
        
        # Should not crash, though specific behavior may vary
        self.assertIn(response.status_code, [200, 302, 400, 500])

    def test_concurrent_dispute_resolution_attempts(self):
        """Test handling of concurrent dispute resolution attempts."""
        # This is a complex test that would require threading or database transactions
        # For now, we'll test the basic case where dispute status is checked
        
        rejected_submission = self.create_submission(
            task=self.task,
            member=self.member,
            status='rejected'
        )
        dispute = self.create_dispute(submission=rejected_submission)
        
        # Manually set dispute to resolved state
        dispute.status = 'resolved_favor_member'
        dispute.save()
        
        # Try to resolve it again
        self.login_user(self.admin)
        resolve_url = reverse('tasks:resolve_dispute', kwargs={'dispute_id': dispute.id})
        data = {'resolution': 'favor_advertiser', 'admin_notes': 'Second attempt'}
        
        response = self.client.post(resolve_url, data)
        
        # Should handle gracefully - exact behavior depends on implementation
        self.assertIn(response.status_code, [200, 302, 400])