

# tests/test_admin.py
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from referrals.models import ReferralCode, Referral, ReferralEarning, CommissionTier
from referrals.admin import (
    ReferralCodeAdmin, ReferralAdmin, ReferralEarningAdmin, CommissionTierAdmin
)

User = get_user_model()


class MockRequest:
    """Mock request object for admin tests"""
    pass


class AdminTests(TestCase):
    """Test cases for admin functionality"""
    
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        
        # Create test users
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.referrer = User.objects.create_user(
            username='referrer',
            email='referrer@example.com',
            password='testpass123'
        )
        
        # Create test data
        self.referral_code = ReferralCode.objects.get(user=self.user)
        self.referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.user,
            level=1,
            referral_code=ReferralCode.objects.get(user=self.referrer)
        )
        self.earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.user,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='pending'
        )
        self.commission_tier = CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
    
    def test_referral_code_admin_list_display(self):
        """Test ReferralCodeAdmin list display"""
        admin = ReferralCodeAdmin(ReferralCode, self.site)
        
        # Test referral_count method
        count = admin.referral_count(self.referral_code)
        expected_count = self.referral_code.referral_set.count()
        self.assertEqual(count, expected_count)
    
    def test_referral_admin_list_display(self):
        admin = ReferralAdmin(Referral, self.site)

        ReferralEarning.objects.create(referral=self.referral, amount=Decimal("10.00"), status="approved")
        ReferralEarning.objects.create(referral=self.referral, amount=Decimal("25.00"), status="paid")

        total = admin.total_earnings(self.referral)

        self.assertEqual(total, "$35.00")

    
    def test_referral_earning_admin_display_methods(self):
        """Test ReferralEarningAdmin display methods"""
        admin = ReferralEarningAdmin(ReferralEarning, self.site)
        
        # Test amount_display
        amount_display = admin.amount_display(self.earning)
        self.assertEqual(amount_display, '$25.00')
        
        # Test status_display
        status_display = admin.status_display(self.earning)
        self.assertIn('orange', status_display)  # Pending is orange
        self.assertIn('Pending', status_display)
        
        # Test level_display
        level_display = admin.level_display(self.earning)
        self.assertEqual(level_display, 'Level 1')
        
        # Test transaction_link with no transaction
        transaction_link = admin.transaction_link(self.earning)
        self.assertEqual(transaction_link, '-')
    
    @patch('referrals.admin.reverse')
    def test_referral_earning_admin_transaction_link_with_transaction(self, mock_reverse):
        """Test transaction link when transaction exists"""
        mock_reverse.return_value = '/admin/wallets/transaction/?q=123'
        
        self.earning.transaction_id = '123'
        self.earning.save()
        
        admin = ReferralEarningAdmin(ReferralEarning, self.site)
        transaction_link = admin.transaction_link(self.earning)
        
        self.assertIn('View Transaction', transaction_link)
        self.assertIn('href=', transaction_link)
    
    def test_referral_earning_admin_approve_action(self):
        """Test approve earnings admin action"""
        admin = ReferralEarningAdmin(ReferralEarning, self.site)
        request = MockRequest()
        
        queryset = ReferralEarning.objects.filter(id=self.earning.id)
        
        # Mock message_user method
        admin.message_user = Mock()
        
        admin.approve_earnings(request, queryset)
        
        # Check that earning was approved
        self.earning.refresh_from_db()
        self.assertEqual(self.earning.status, 'approved')
        self.assertIsNotNone(self.earning.approved_at)
        
        # Check that message was sent
        admin.message_user.assert_called_once()
    
    def test_referral_earning_admin_mark_paid_action(self):
        """Test mark as paid admin action"""
        # First approve the earning
        self.earning.status = 'approved'
        self.earning.approved_at = timezone.now()
        self.earning.save()
        
        admin = ReferralEarningAdmin(ReferralEarning, self.site)
        request = MockRequest()
        
        queryset = ReferralEarning.objects.filter(id=self.earning.id)
        admin.message_user = Mock()
        
        admin.mark_as_paid(request, queryset)
        
        # Check that earning was marked as paid
        self.earning.refresh_from_db()
        self.assertEqual(self.earning.status, 'paid')
        self.assertIsNotNone(self.earning.paid_at)
        
        admin.message_user.assert_called_once()
    
    def test_referral_earning_admin_cancel_action(self):
        """Test cancel earnings admin action"""
        admin = ReferralEarningAdmin(ReferralEarning, self.site)
        request = MockRequest()
        
        queryset = ReferralEarning.objects.filter(id=self.earning.id)
        admin.message_user = Mock()
        
        admin.cancel_earnings(request, queryset)
        
        # Check that earning was cancelled
        self.earning.refresh_from_db()
        self.assertEqual(self.earning.status, 'cancelled')
        
        admin.message_user.assert_called_once()
    
    def test_commission_tier_admin_rate_display(self):
        """Test CommissionTierAdmin rate display"""
        admin = CommissionTierAdmin(CommissionTier, self.site)
        
        rate_display = admin.rate_display(self.commission_tier)
        self.assertEqual(rate_display, '10.00%')
    
    def test_admin_actions_only_affect_eligible_records(self):
        """Test that admin actions only affect eligible records"""
        # Create earning that's already paid
        paid_earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.user,
            referral=self.referral,
            amount=Decimal('50.00'),
            earning_type='advertiser_funding',
            commission_rate=Decimal('2.00'),
            status='paid'
        )
        
        admin = ReferralEarningAdmin(ReferralEarning, self.site)
        request = MockRequest()
        admin.message_user = Mock()
        
        # Try to approve paid earning (should not change)
        queryset = ReferralEarning.objects.filter(id=paid_earning.id)
        admin.approve_earnings(request, queryset)
        
        paid_earning.refresh_from_db()
        self.assertEqual(paid_earning.status, 'paid')  # Should remain paid
    
    def test_admin_bulk_actions(self):
        """Test admin bulk actions with multiple records"""
        # Create multiple pending earnings
        earnings = []
        for i in range(3):
            earning = ReferralEarning.objects.create(
                referrer=self.referrer,
                referred_user=self.user,
                referral=self.referral,
                amount=Decimal(f'{10 + i}.00'),
                earning_type='signup',
                commission_rate=Decimal('0.00'),
                status='pending'
            )
            earnings.append(earning)
        
        admin = ReferralEarningAdmin(ReferralEarning, self.site)
        request = MockRequest()
        admin.message_user = Mock()
        
        # Approve all at once
        queryset = ReferralEarning.objects.filter(
            id__in=[e.id for e in earnings]
        )
        admin.approve_earnings(request, queryset)
        
        # All should be approved
        for earning in earnings:
            earning.refresh_from_db()
            self.assertEqual(earning.status, 'approved')
            self.assertIsNotNone(earning.approved_at)
