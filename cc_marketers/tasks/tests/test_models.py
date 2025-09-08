# tests/test_models.py
"""
Comprehensive test suite for Task app models.
Tests model methods, properties, validations, and relationships.
"""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta
import uuid

from tasks.models import Task, Submission, Dispute, TaskWallet, TaskWalletTransaction
from .test_base import ComprehensiveTaskTestCase


class TaskModelTest(ComprehensiveTaskTestCase):
    """Test cases for Task model."""
    
    def test_task_creation(self):
        """Test basic task creation."""
        task = self.create_task(
            title='New Task',
            description='Task description',
            payout_per_slot=Decimal('15.50'),
            total_slots=3
        )
        
        self.assertEqual(task.title, 'New Task')
        self.assertEqual(task.payout_per_slot, Decimal('15.50'))
        self.assertEqual(task.total_slots, 3)
        self.assertEqual(task.remaining_slots, 3)  # Should auto-populate
        self.assertEqual(task.status, 'active')
        self.assertIsNotNone(task.created_at)
        self.assertIsNotNone(task.updated_at)

    def test_task_string_representation(self):
        """Test task __str__ method."""
        task = self.create_task(title='Test Task Title')
        self.assertEqual(str(task), 'Test Task Title')

    def test_task_save_sets_remaining_slots(self):
        """Test that remaining_slots is set to total_slots on creation."""
        task = Task(
            advertiser=self.advertiser,
            title='Test Task',
            description='Description',
            payout_per_slot=Decimal('10.00'),
            total_slots=5,
            deadline=timezone.now() + timedelta(days=7),
            proof_instructions='Instructions'
        )
        # Don't set remaining_slots manually
        task.save()
        
        self.assertEqual(task.remaining_slots, 5)

    def test_task_is_full_property(self):
        """Test is_full property."""
        task = self.create_task(total_slots=3)
        
        # Initially not full
        self.assertFalse(task.is_full)
        
        # Make it full
        task.remaining_slots = 0
        task.save()
        self.assertTrue(task.is_full)

    def test_task_is_expired_property(self):
        """Test is_expired property."""
        # Future deadline - not expired
        future_task = self.create_task(
            deadline=timezone.now() + timedelta(hours=1)
        )
        self.assertFalse(future_task.is_expired)
        
        # Past deadline - expired
        past_task = self.create_task(
            title='Past Task',
            deadline=timezone.now() - timedelta(hours=1)
        )
        self.assertTrue(past_task.is_expired)

    def test_task_total_payout_property(self):
        """Test total_payout property calculation."""
        task = self.create_task(
            payout_per_slot=Decimal('12.50'),
            total_slots=4
        )
        expected_total = Decimal('12.50') * 4
        self.assertEqual(task.total_payout, expected_total)

    def test_task_filled_slots_property(self):
        """Test filled_slots property calculation."""
        task = self.create_task(total_slots=5)
        
        # Initially no filled slots
        self.assertEqual(task.filled_slots, 0)
        
        # Fill some slots
        task.remaining_slots = 2
        task.save()
        self.assertEqual(task.filled_slots, 3)

    def test_task_minimum_payout_validation(self):
        """Test that minimum payout validation works."""
        with self.assertRaises(ValidationError):
            task = Task(
                advertiser=self.advertiser,
                title='Invalid Task',
                description='Description',
                payout_per_slot=Decimal('0.00'),  # Invalid - below minimum
                total_slots=1,
                deadline=timezone.now() + timedelta(days=1),
                proof_instructions='Instructions'
            )
            task.full_clean()

    def test_task_minimum_slots_validation(self):
        """Test that minimum slots validation works."""
        with self.assertRaises(ValidationError):
            task = Task(
                advertiser=self.advertiser,
                title='Invalid Task',
                description='Description',
                payout_per_slot=Decimal('10.00'),
                total_slots=0,  # Invalid - below minimum
                deadline=timezone.now() + timedelta(days=1),
                proof_instructions='Instructions'
            )
            task.full_clean()

    def test_task_ordering(self):
        """Test that tasks are ordered by creation date (newest first)."""
        task1 = self.create_task(title='First Task')
        task2 = self.create_task(title='Second Task')
        
        tasks = Task.objects.all()
        self.assertEqual(tasks[0], task2)  # Newest first
        self.assertEqual(tasks[1], task1)


class SubmissionModelTest(ComprehensiveTaskTestCase):
    """Test cases for Submission model."""
    
    def test_submission_creation(self):
        """Test basic submission creation."""
        submission = self.create_submission(
            proof_text='Completed the task as requested'
        )
        
        self.assertEqual(submission.task, self.task)
        self.assertEqual(submission.member, self.member)
        self.assertEqual(submission.proof_text, 'Completed the task as requested')
        self.assertEqual(submission.status, 'pending')
        self.assertIsNotNone(submission.submitted_at)
        self.assertIsNone(submission.reviewed_at)

    def test_submission_string_representation(self):
        """Test submission __str__ method."""
        submission = self.create_submission()
        expected = f"{self.member.get_display_name()} - {self.task.title}"
        self.assertEqual(str(submission), expected)

    def test_submission_unique_constraint(self):
        """Test that user can't submit multiple times to same task."""
        # Create first submission
        self.create_submission()
        
        # Try to create second submission - should fail
        with self.assertRaises(IntegrityError):
            self.create_submission()

    def test_submission_approve_method(self):
        """Test submission approve method."""
        submission = self.create_submission()
        
        submission.approve(self.admin)
        
        self.assertEqual(submission.status, 'approved')
        self.assertEqual(submission.reviewed_by, self.admin)
        self.assertIsNotNone(submission.reviewed_at)

    def test_submission_reject_method(self):
        """Test submission reject method."""
        submission = self.create_submission()
        reason = 'Did not follow instructions'
        
        submission.reject(self.admin, reason)
        
        self.assertEqual(submission.status, 'rejected')
        self.assertEqual(submission.reviewed_by, self.admin)
        self.assertEqual(submission.rejection_reason, reason)
        self.assertIsNotNone(submission.reviewed_at)

    def test_submission_ordering(self):
        """Test that submissions are ordered by submission date (newest first)."""
        # Create submissions with slight time difference
        self.create_submission(member=self.member)
        
        # Create another user and task to avoid unique constraint
        another_member = self.create_user('another_member', 'another@test.com')
        submission2 = self.create_submission(member=another_member)
        
        submissions = Submission.objects.all()
        self.assertEqual(submissions[0], submission2)  # Newest first


class DisputeModelTest(ComprehensiveTaskTestCase):
    """Test cases for Dispute model."""
    
    def test_dispute_creation(self):
        """Test basic dispute creation."""
        rejected_submission = self.create_submission(status='rejected')
        dispute = self.create_dispute(
            submission=rejected_submission,
            reason='Unfair rejection'
        )
        
        self.assertEqual(dispute.submission, rejected_submission)
        self.assertEqual(dispute.raised_by, self.member)
        self.assertEqual(dispute.reason, 'Unfair rejection')
        self.assertEqual(dispute.status, 'open')
        self.assertIsNotNone(dispute.created_at)
        self.assertIsNone(dispute.resolved_at)

    def test_dispute_string_representation(self):
        """Test dispute __str__ method."""
        dispute = self.create_dispute()
        expected = f"Dispute #{dispute.id} - {dispute.submission.task.title}"
        self.assertEqual(str(dispute), expected)

    def test_dispute_one_to_one_relationship(self):
        """Test that submission can only have one dispute."""
        rejected_submission = self.create_submission(status='rejected')
        
        # Create first dispute
        self.create_dispute(submission=rejected_submission)
        
        # Try to create second dispute for same submission
        with self.assertRaises(IntegrityError):
            self.create_dispute(submission=rejected_submission)

    def test_dispute_ordering(self):
        """Test that disputes are ordered by creation date (newest first)."""
        self.create_dispute()
        
        # Create another rejected submission for second dispute
        rejected_submission2 = self.create_submission(
            task=self.create_task(title='Another Task'),
            status='rejected'
        )
        dispute2 = self.create_dispute(
            submission=rejected_submission2,
            reason='Another dispute'
        )
        
        disputes = Dispute.objects.all()
        self.assertEqual(disputes[0], dispute2)  # Newest first


class TaskWalletModelTest(ComprehensiveTaskTestCase):
    """Test cases for TaskWallet model."""
    
    def test_task_wallet_creation(self):
        """Test basic task wallet creation."""
        user = self.create_user('testuser', 'test@example.com')
        wallet = TaskWallet.objects.create(user=user)
        
        self.assertEqual(wallet.user, user)
        self.assertEqual(wallet.balance, Decimal('0.00'))
        self.assertIsNotNone(wallet.created_at)
        self.assertIsNotNone(wallet.updated_at)

    def test_task_wallet_string_representation(self):
        """Test task wallet __str__ method."""
        wallet, _  = TaskWallet.objects.get_or_create(
            user=self.advertiser,
        )
        wallet.balance=Decimal('150.75')
        wallet.save()

        expected = f"Task Wallet - {self.advertiser.username}: $150.75"
        self.assertEqual(str(wallet), expected)

    def test_task_wallet_get_available_balance(self):
        """Test get_available_balance method."""
        wallet, _ = TaskWallet.objects.get_or_create(user=self.advertiser)
        wallet.balance=Decimal('200.00')
        wallet.save()

        self.assertEqual(wallet.get_available_balance(), Decimal('200.00'))

    def test_task_wallet_one_per_user(self):
        """Test that each user can only have one task wallet."""
        # Create first wallet
        TaskWallet.objects.get_or_create(user=self.advertiser)
        
        # Try to create second wallet for same user
        with self.assertRaises(IntegrityError):
            TaskWallet.objects.create(user=self.advertiser, balance=Decimal("50.00"))


class TaskWalletTransactionModelTest(ComprehensiveTaskTestCase):
    """Test cases for TaskWalletTransaction model."""
    
    def test_transaction_creation(self):
        """Test basic transaction creation."""
        transaction = TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='credit',
            category='topup_from_main',
            amount=Decimal('50.00'),
            balance_before=Decimal('100.00'),
            balance_after=Decimal('150.00')
        )
        
        self.assertEqual(transaction.user, self.advertiser)
        self.assertEqual(transaction.transaction_type, 'credit')
        self.assertEqual(transaction.category, 'topup_from_main')
        self.assertEqual(transaction.amount, Decimal('50.00'))
        self.assertEqual(transaction.status, 'success')  # Default value
        self.assertIsNotNone(transaction.created_at)
        self.assertTrue(isinstance(transaction.id, uuid.UUID))

    def test_transaction_string_representation(self):
        """Test transaction __str__ method."""
        transaction = TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='debit',
            category='task_posting',
            amount=Decimal('25.50'),
            balance_before=Decimal('100.00'),
            balance_after=Decimal('74.50')
        )
        expected = f"{self.advertiser.username} - debit $25.50 (task_posting)"
        self.assertEqual(str(transaction), expected)

    def test_transaction_minimum_amount_validation(self):
        """Test that minimum amount validation works."""
        with self.assertRaises(ValidationError):
            transaction = TaskWalletTransaction(
                user=self.advertiser,
                transaction_type='credit',
                category='topup_from_main',
                amount=Decimal('0.00'),  # Invalid - below minimum
                balance_before=Decimal('100.00'),
                balance_after=Decimal('100.00')
            )
            transaction.full_clean() 

    def test_transaction_ordering(self):
        """Test that transactions are ordered by creation date (newest first)."""
        TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='credit',
            category='topup_from_main',
            amount=Decimal('50.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50.00')
        )
        
        transaction2 = TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='debit',
            category='task_posting',
            amount=Decimal('20.00'),
            balance_before=Decimal('50.00'),
            balance_after=Decimal('30.00')
        )
        
        transactions = TaskWalletTransaction.objects.all()
        self.assertEqual(transactions[0], transaction2)  # Newest first

    def test_transaction_unique_reference(self):
        """Test that reference field must be unique when provided."""
        # Create first transaction with reference
        TaskWalletTransaction.objects.create(
            user=self.advertiser,
            transaction_type='credit',
            category='topup_from_main',
            amount=Decimal('50.00'),
            balance_before=Decimal('0.00'),
            balance_after=Decimal('50.00'),
            reference='TXN123'
        )
        
        # Try to create second transaction with same reference
        with self.assertRaises(IntegrityError):
            TaskWalletTransaction.objects.create(
                user=self.member,
                transaction_type='credit',
                category='topup_from_main',
                amount=Decimal('25.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('25.00'),
                reference='TXN123'  # Duplicate reference
            )

    def test_transaction_choices_validation(self):
        """Test that choice fields only accept valid values."""
        # Test invalid transaction_type
        with self.assertRaises(ValidationError):
            transaction = TaskWalletTransaction(
                user=self.advertiser,
                transaction_type='invalid_type',
                category='topup_from_main',
                amount=Decimal('50.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('50.00')
            )
            transaction.full_clean()
        
        # Test invalid category
        with self.assertRaises(ValidationError):
            transaction = TaskWalletTransaction(
                user=self.advertiser,
                transaction_type='credit',
                category='invalid_category',
                amount=Decimal('50.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('50.00')
            )
            transaction.full_clean()
        
        # Test invalid status
        with self.assertRaises(ValidationError):
            transaction = TaskWalletTransaction(
                user=self.advertiser,
                transaction_type='credit',
                category='topup_from_main',
                amount=Decimal('50.00'),
                balance_before=Decimal('0.00'),
                balance_after=Decimal('50.00'),
                status='invalid_status'
            )
            transaction.full_clean()


class ModelIntegrationTest(ComprehensiveTaskTestCase):
    """Test model integrations and complex scenarios."""
    
    def test_task_submission_relationship(self):
        """Test the relationship between tasks and submissions."""
        # Create multiple submissions for the task
        submission1 = self.create_submission(member=self.member)
        
        another_member = self.create_user('another', 'another@test.com')
        submission2 = self.create_submission(member=another_member)
        
        # Test reverse relationship
        task_submissions = self.task.submissions.all()
        self.assertEqual(len(task_submissions), 2)
        self.assertIn(submission1, task_submissions)
        self.assertIn(submission2, task_submissions)

    def test_cascading_deletes(self):
        """Test that related objects are properly deleted on cascade."""
        # Create submission and dispute
        submission = self.create_submission()
        dispute = self.create_dispute(submission=submission)
        
        # Delete the user - should cascade to submissions and disputes
        self.member.id
        submission_id = submission.id
        dispute_id = dispute.id
        
        self.member.delete()
        
        # Check that submission and dispute are deleted
        self.assertFalse(Submission.objects.filter(id=submission_id).exists())
        self.assertFalse(Dispute.objects.filter(id=dispute_id).exists())

    def test_task_wallet_balance_precision(self):
        """Test that wallet balance maintains proper decimal precision."""
        wallet, _ = TaskWallet.objects.get_or_create(
            user=self.advertiser,
              # More than 2 decimal places
        )
        wallet.balance=Decimal('123.456')
        wallet.save()
        
        
        # Should be rounded to 2 decimal places
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal('123.46'))

    def test_complex_task_lifecycle(self):
        """Test complete task lifecycle with submissions and disputes."""
        # Create task
        task = self.create_task(total_slots=2, payout_per_slot=Decimal('20.00'))
        
        # Create submissions
        submission1 = self.create_submission(task=task, member=self.member)
        
        another_member = self.create_user('another', 'another@test.com')
        submission2 = self.create_submission(task=task, member=another_member)
        
        # Approve first submission
        submission1.approve(self.admin)
        
        # Reject second submission
        submission2.reject(self.admin, 'Incomplete work')
        
        # Create dispute for rejected submission
        dispute = self.create_dispute(submission=submission2)
        
        # Verify relationships and states
        self.assertEqual(task.submissions.count(), 2)
        self.assertEqual(task.submissions.filter(status='approved').count(), 1)
        self.assertEqual(task.submissions.filter(status='rejected').count(), 1)
        self.assertTrue(hasattr(submission2, 'dispute'))
        self.assertEqual(submission2.dispute, dispute)