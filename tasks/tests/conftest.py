
# tests/conftest.py (if using pytest)
"""
Pytest configuration and fixtures for the task app test suite.
"""
import pytest
from django.contrib.auth import get_user_model
from decimal import Decimal

from tasks.services import TaskWalletService
from wallets.services import WalletService

User = get_user_model()


@pytest.fixture
def admin_user(db):
    """Create admin user for tests."""
    return User.objects.create_superuser(
        username='admin',
        email='admin@test.com',
        password='testpass123'
    )


@pytest.fixture
def advertiser_user(db):
    """Create advertiser user for tests."""
    user = User.objects.create_user(
        username='advertiser',
        email='advertiser@test.com',
        password='testpass123'
    )
    user.role = 'advertiser'
    user.is_subscribed = True
    user.save()
    return user


@pytest.fixture
def member_user(db):
    """Create member user for tests."""
    user = User.objects.create_user(
        username='member',
        email='member@test.com',
        password='testpass123'
    )
    user.role = 'member'
    user.is_subscribed = True
    user.save()
    return user


@pytest.fixture
def setup_wallets(advertiser_user, member_user):
    """Set up wallets with initial balances."""
    # Main wallets
    advertiser_wallet = WalletService.get_or_create_wallet(advertiser_user)
    advertiser_wallet.balance = Decimal('1000.00')
    advertiser_wallet.save()
    
    member_wallet = WalletService.get_or_create_wallet(member_user)
    member_wallet.balance = Decimal('100.00')
    member_wallet.save()
    
    # Task wallets
    advertiser_task_wallet = TaskWalletService.get_or_create_wallet(advertiser_user)
    advertiser_task_wallet.balance = Decimal('500.00')
    advertiser_task_wallet.save()
    
    return {
        'advertiser_wallet': advertiser_wallet,
        'member_wallet': member_wallet,
        'advertiser_task_wallet': advertiser_task_wallet
    }

