# tests/test_base.py
from django.test import TestCase, RequestFactory, TransactionTestCase

from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from subscriptions.models import SubscriptionPlan, UserSubscription
from wallets.models import Wallet, WithdrawalRequest
from tasks.models import TaskWallet, TaskWalletTransaction

User = get_user_model()


class BaseTestMixin:
    """Base mixin with common test setup and utilities"""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.user = self.create_user()
        self.user2 = self.create_user(username='testuser2', email='test2@example.com')
        self.admin_user = self.create_user(username='admin', email='admin@example.com', is_staff=True)
        
        # Create subscription plans
        self.basic_plan = self.create_subscription_plan(
            name='Basic Plan',
            price=Decimal('5.00'),
            daily_ad_limit=10
        )
        
        self.business_plan = self.create_subscription_plan(
            name='Business Member Account',
            price=Decimal('15.00'),
            business_volume=1000,
            referral_commission=Decimal('2.00'),
            commission_to_tree=Decimal('1.00'),
            daily_ad_limit=50
        )
        
        self.premium_plan = self.create_subscription_plan(
            name='Premium Plan',
            price=Decimal('25.00'),
            duration_days=365,
            daily_ad_limit=0  # unlimited
        )
        
        # Create wallets
        self.wallet = self.create_wallet(self.user, balance=Decimal('100.00'))
        self.wallet2 = self.create_wallet(self.user2, balance=Decimal('50.00'))
        
        # Create task wallets
        self.task_wallet = self.create_task_wallet(self.user, balance=Decimal('0.00'))
        self.task_wallet2 = self.create_task_wallet(self.user2, balance=Decimal('5.00'))

    def create_user(self, username='testuser', email='test@example.com', **kwargs):
        """Create a test user"""
        defaults = {
            'username': username,
            'email': email,
            'first_name': 'Test',
            'last_name': 'User'
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    def create_subscription_plan(self, **kwargs):
        """Create a subscription plan"""
        defaults = {
            'name': 'Test Plan',
            'price': Decimal('10.00'),
            'duration_days': 30,
            'business_volume': 500,
            'referral_commission': Decimal('1.00'),
            'commission_to_tree': Decimal('0.50'),
            'daily_ad_limit': 20,
            'is_active': True
        }
        defaults.update(kwargs)
        return SubscriptionPlan.objects.create(**defaults)

    def create_wallet(self, user, balance=Decimal('0.00')):
        """Create a wallet for user"""
        return Wallet.objects.create(user=user, balance=balance)

    def create_task_wallet(self, user, balance=Decimal('0.00')):
        """Create a task wallet for user"""
        return TaskWallet.objects.create(user=user, balance=balance)

    def create_subscription(self, user=None, plan=None, **kwargs):
        """Create a user subscription"""
        if user is None:
            user = self.user
        if plan is None:
            plan = self.basic_plan
            
        defaults = {
            'user': user,
            'plan': plan,
            'start_date': timezone.now(),
            'expiry_date': timezone.now() + timedelta(days=plan.duration_days),
            'status': 'active',
            'auto_renewal': True
        }
        defaults.update(kwargs)
        return UserSubscription.objects.create(**defaults)

    def create_withdrawal_request(self, user=None, amount=Decimal('10.00'), status='pending'):
        """Create a withdrawal request"""
        if user is None:
            user = self.user
        return WithdrawalRequest.objects.create(
            user=user,
            amount=amount,
            status=status
        )

    def login_user(self, user=None):
        """Login a user"""
        if user is None:
            user = self.user
        self.client.force_login(user)

    def assertDecimalEqual(self, first, second, msg=None, places=2):
        """Assert decimal values are equal"""
        self.assertEqual(round(first, places), round(second, places), msg)


class BaseViewTestCase(BaseTestMixin, TestCase):
    """Base test case for view tests"""
    pass


class BaseTransactionTestCase(BaseTestMixin, TransactionTestCase):
    """Base test case for transaction tests"""
    pass


class MockServices:
    """Mock services for testing"""
    
    @staticmethod
    def mock_credit_signup_bonus_on_subscription(user):
        """Mock referral bonus credit"""
        return True

    @staticmethod
    def mock_wallet_service_credit(user, amount, category, description, reference=None):
        """Mock wallet credit operation"""
        try:
            wallet = Wallet.objects.get(user=user)
            wallet.balance += amount
            wallet.save()
            return True
        except Wallet.DoesNotExist:
            return False

    @staticmethod
    def mock_task_wallet_service_credit(user, amount, category, description):
        """Mock task wallet credit operation"""
        try:
            task_wallet = TaskWallet.objects.get(user=user)
            task_wallet.balance += amount
            task_wallet.save()
            return TaskWalletTransaction.objects.create(
                user=user,
                transaction_type='credit',
                amount=amount,
                category=category,
                description=description
            )
        except TaskWallet.DoesNotExist:
            return None

    @staticmethod
    def mock_task_wallet_service_debit(user, amount, category, description):
        """Mock task wallet debit operation"""
        try:
            task_wallet = TaskWallet.objects.get(user=user)
            if task_wallet.balance >= amount:
                task_wallet.balance -= amount
                task_wallet.save()
                return TaskWalletTransaction.objects.create(
                    user=user,
                    transaction_type='debit',
                    amount=amount,
                    category=category,
                    description=description
                )
            return None
        except TaskWallet.DoesNotExist:
            return None