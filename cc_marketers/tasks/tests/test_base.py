# tests/test_base.py
"""
Base test classes and utilities for the tasks app test suite.
Provides common setup, fixtures, and helper methods to ensure DRY principles.
"""
import tempfile
from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta
from PIL import Image
import io

from tasks.models import Task, Submission, Dispute
from wallets.models import  EscrowTransaction
from wallets.services import WalletService
from tasks.services import TaskWalletService

from subscriptions.models import SubscriptionPlan, UserSubscription

User = get_user_model()

# Create temp media directory for tests
TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class BaseTaskTestCase(TestCase):
    """Base test case with common setup for all task-related tests."""
    
    @classmethod
    def setUpTestData(cls):
        """Set up test data that doesn't change between test methods."""
        # Create users with different roles
        cls.advertiser = cls.create_user(
            username='advertiser',
            email='advertiser@test.com',
            role='advertiser',
            is_subscribed=True
        )
        
        cls.member = cls.create_user(
            username='member',
            email='member@test.com',
            role='member',
            is_subscribed=True
        )
        
        cls.admin = cls.create_user(
            username='admin',
            email='admin@test.com',
            role='advertiser',
            is_staff=True,
            is_subscribed=True
        )
        
        cls.unsubscribed_user = cls.create_user(
            username='unsubscribed',
            email='unsubscribed@test.com',
            role='member',
            is_subscribed=False
        )
        
        # Create company system user
        cls.company_user = cls.create_user(
            username='company_system',
            email='company@test.com',
            role='advertiser'
        )

    def setUp(self):
        """Set up test data that may change between test methods."""
        # Setup wallets with sufficient balance
        self.advertiser_wallet = WalletService.get_or_create_wallet(self.advertiser)
        self.advertiser_wallet.balance = Decimal('1000.00')
        self.advertiser_wallet.save()
        
        self.member_wallet = WalletService.get_or_create_wallet(self.member)
        self.member_wallet.balance = Decimal('100.00')
        self.member_wallet.save()
        
        # Setup task wallets
        self.advertiser_task_wallet = TaskWalletService.get_or_create_wallet(self.advertiser)
        self.advertiser_task_wallet.balance = Decimal('500.00')
        self.advertiser_task_wallet.save()
        
        # Create a sample task
        self.task = self.create_task(
            advertiser=self.advertiser,
            title='Test Task',
            description='Test task description',
            payout_per_slot=Decimal('10.00'),
            total_slots=5
        )
        
        # Create escrow for the task
        self.escrow = EscrowTransaction.objects.create(
            task=self.task,
            advertiser=self.advertiser,
            amount=Decimal('50.00'),
            status='locked'
        )



    @classmethod
    def create_user(cls, username, email, role='member', is_subscribed=False, is_staff=False, **kwargs):
        user = User.objects.create_user(
            username=username,
            email=email,
            is_staff=is_staff,
            **kwargs
        )
        user.role = role
        user.save()

        # 🔑 If is_subscribed=True, attach a subscription
        if is_subscribed:
            plan = SubscriptionPlan.objects.first()
            if not plan:
                # Create a default test plan if none exists
                plan = SubscriptionPlan.objects.create(
                    name="Business Member Plan",
                    price=0,
                    duration_days=30,
                    business_volume=0,
                    referral_commission=0,
                    commission_to_tree=0,
                    daily_ad_limit=100000,
                )
            UserSubscription.objects.create(
                user=user,
                plan=plan,
                expiry_date=timezone.now() + timezone.timedelta(days=30),
                status="active"
            )

        return user
    
    def create_task(self, advertiser=None, title='Sample Task', description='Sample description',
                payout_per_slot=Decimal('5.00'), total_slots=3, deadline=None,
                remaining_slots=None, **kwargs):
        """Helper method to create tasks."""
        if advertiser is None:
            advertiser = self.advertiser
        if deadline is None:
            deadline = timezone.now() + timedelta(days=7)

        task = Task.objects.create(
            advertiser=advertiser,
            title=title,
            description=description,
            payout_per_slot=payout_per_slot,
            total_slots=total_slots,
            deadline=deadline,
            proof_instructions='Provide proof of completion',
            **kwargs
        )

        # ✅ Force remaining_slots if provided
        if remaining_slots is not None:
            task.remaining_slots = remaining_slots
            task.save(update_fields=['remaining_slots'])

        return task

    def create_submission(self, task=None, member=None, status='pending', **kwargs):
        """Helper method to create submissions."""
        if task is None:
            task = self.task
        if member is None:
            member = self.member

        proof_text = kwargs.pop('proof_text', 'Sample proof text')

        submission = Submission.objects.create(
            task=task,
            member=member,
            proof_text=proof_text,
            status=status,
            **kwargs
        )
        return submission


    def create_dispute(self, submission=None, raised_by=None, reason='Test dispute reason', **kwargs):
        """Helper method to create disputes."""
        if submission is None:
            # Create a rejected submission first
            submission = self.create_submission(status='rejected')
        if raised_by is None:
            raised_by = submission.member
        
        dispute = Dispute.objects.create(
            submission=submission,
            raised_by=raised_by,
            reason=reason,
            **kwargs
        )
        return dispute

    def create_test_image(self, name='test.jpg', size=(100, 100)):
        """Create a test image file for uploads."""
        image = Image.new('RGB', size, 'red')
        image_io = io.BytesIO()
        image.save(image_io, format='JPEG')
        image_io.seek(0)
        return SimpleUploadedFile(name, image_io.getvalue(), content_type='image/jpeg')

    def create_test_file(self, name='test.txt', content=b'test file content'):
        """Create a test file for uploads."""
        return SimpleUploadedFile(name, content, content_type='text/plain')

    def login_user(self, user):
        """Helper method to log in a user."""
        self.client.force_login(user)

    def assert_requires_login(self, url, method='get'):
        """Assert that a URL requires login."""
        response = getattr(self.client, method)(url)
        self.assertRedirects(response, f'/login/?next={url}')

    def assert_permission_denied(self, url, user, method='get', **kwargs):
        """Assert that a user gets permission denied for a URL."""
        self.login_user(user)
        response = getattr(self.client, method)(url, **kwargs)
        self.assertIn(response.status_code, [403, 302])  # Forbidden or redirect with error

    def assert_subscription_required(self, url, method='get', **kwargs):
        """Assert that a URL requires subscription."""
        self.login_user(self.unsubscribed_user)
        response = getattr(self.client, method)(url, **kwargs)
        # This depends on how subscription_required decorator works
        # Adjust based on your implementation
        self.assertIn(response.status_code, [302, 403])

    def refresh_from_db(self, *objects):
        """Refresh multiple objects from database."""
        for obj in objects:
            obj.refresh_from_db()

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        super().tearDownClass()
        # Clean up test media files
        import shutil
        try:
            shutil.rmtree(TEST_MEDIA_ROOT)
        except OSError:
            pass


class TaskTestMixin:
    """Mixin providing task-specific test utilities."""
    
    def assert_task_escrow_locked(self, task, expected_amount):
        """Assert that escrow is properly locked for a task."""
        escrow = EscrowTransaction.objects.get(task=task)
        self.assertEqual(escrow.status, 'locked')
        self.assertEqual(escrow.amount, expected_amount)

    def assert_task_escrow_released(self, task):
        """Assert that escrow is released for a task."""
        escrow = EscrowTransaction.objects.get(task=task)
        self.assertEqual(escrow.status, 'released')
        self.assertIsNotNone(escrow.released_at)

    def assert_wallet_balance(self, user, expected_balance, wallet_type='main'):
        """Assert wallet balance for a user."""
        if wallet_type == 'main':
            wallet = WalletService.get_or_create_wallet(user)
        else:
            wallet = TaskWalletService.get_or_create_wallet(user)
        
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal(str(expected_balance)))

    def assert_transaction_created(self, user, transaction_type, amount, category=None):
        """Assert that a wallet transaction was created."""
        from wallets.models import Transaction
        
        transaction = Transaction.objects.filter(
            user=user,
            transaction_type=transaction_type,
            amount=amount
        ).order_by('-created_at').first()
        
        self.assertIsNotNone(transaction)
        if category:
            self.assertEqual(transaction.category, category)


class FormTestMixin:
    """Mixin providing form testing utilities."""
    
    def assert_form_error(self, response, form_name, field, error_message=None):
        """Assert that a form has errors."""
        form = response.context.get(form_name)
        self.assertIsNotNone(form, f"Form '{form_name}' not found in context")
        self.assertTrue(form.errors, "Form should have errors")
        if field:
            self.assertIn(field, form.errors)
        if error_message:
            self.assertIn(error_message, str(form.errors[field]))

    def assert_form_valid(self, response, form_name):
        """Assert that a form is valid."""
        form = response.context.get(form_name)
        self.assertIsNotNone(form, f"Form '{form_name}' not found in context")
        self.assertFalse(form.errors, f"Form should be valid but has errors: {form.errors}")


class ViewTestMixin:
    """Mixin providing view testing utilities."""
    
    def assert_template_used(self, response, template_name):
        """Assert that the correct template is used."""
        self.assertTemplateUsed(response, template_name)

    def assert_context_contains(self, response, **expected_context):
        """Assert that response context contains expected values."""
        for key, value in expected_context.items():
            self.assertIn(key, response.context)
            if value is not None:
                self.assertEqual(response.context[key], value)

    def assert_message_level(self, response, level, message_text=None):
        """Assert that a message of specific level exists."""
        messages = list(response.context.get('messages', []))
        message_levels = [msg.level for msg in messages]
        self.assertIn(level, message_levels)
        
        if message_text:
            message_texts = [str(msg) for msg in messages]
            self.assertTrue(
                any(message_text in text for text in message_texts),
                f"Message '{message_text}' not found in {message_texts}"
            )

    def assert_success_message(self, response, message_text=None):
        """Assert that a success message exists."""
        from django.contrib import messages
        self.assert_message_level(response, messages.SUCCESS, message_text)

    def assert_error_message(self, response, message_text=None):
        """Assert that an error message exists."""
        from django.contrib import messages
        self.assert_message_level(response, messages.ERROR, message_text)


# Combine all mixins into a comprehensive base class
class ComprehensiveTaskTestCase(BaseTaskTestCase, TaskTestMixin, FormTestMixin, ViewTestMixin):
    """
    Comprehensive base test case combining all mixins.
    Use this as the base class for most task-related tests.
    """
    pass