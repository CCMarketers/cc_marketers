# tests/test_utils.py
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch

from referrals.models import ReferralCode, Referral, ReferralEarning, CommissionTier
from referrals.utils import (
    process_referral_signup, create_multi_tier_referrals,
    calculate_referral_commission, get_referral_stats
)

User = get_user_model()


class UtilsTests(TestCase):
    """Test cases for utility functions"""
    
    def setUp(self):
        self.referrer = User.objects.create_user(
            username='referrer',
            email='referrer@example.com',
            password='testpass123'
        )
        self.new_user = User.objects.create_user(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        self.referral_code, _ = ReferralCode.objects.get_or_create(
            user=self.referrer,
            
        )
    
    def test_process_referral_signup_success(self):
        """Test successful referral signup processing"""
        referral = process_referral_signup(self.new_user, self.referral_code.code)
        
        self.assertIsNotNone(referral)
        self.assertEqual(referral.referrer, self.referrer)
        self.assertEqual(referral.referred, self.new_user)
        self.assertEqual(referral.level, 1)
        self.assertEqual(referral.referral_code, self.referral_code)
    
    def test_process_referral_signup_invalid_code(self):
        """Test referral signup with invalid code"""
        referral = process_referral_signup(self.new_user, 'INVALID')
        self.assertIsNone(referral)
    
    def test_process_referral_signup_inactive_code(self):
        """Test referral signup with inactive code"""
        self.referral_code.is_active = False
        self.referral_code.save()
        
        referral = process_referral_signup(self.new_user, self.referral_code.code )
        self.assertIsNone(referral)
    
    def test_process_referral_signup_self_referral(self):
        """Test that self-referral is prevented"""
        referral = process_referral_signup(self.referrer, self.referral_code.code )
        self.assertIsNone(referral)
    
    @patch('referrals.utils.create_multi_tier_referrals')
    def test_process_referral_signup_calls_multi_tier(self, mock_multi_tier):
        """Test that multi-tier referrals are created"""
        process_referral_signup(self.new_user, self.referral_code.code )
        mock_multi_tier.assert_called_once_with(self.new_user, self.referrer)
    
    def test_create_multi_tier_referrals_complete_chain(self):
        """Test creation of complete 3-level referral chain"""
        # Create referral chain: grandparent -> parent -> direct_referrer
        grandparent = User.objects.create_user(
            username='grandparent',
            email='grandparent@example.com',
            password='testpass123'
        )
        parent = User.objects.create_user(
            username='parent',
            email='parent@example.com',
            password='testpass123'
        )
        
        grandparent_code, _ = ReferralCode.objects.get_or_create(user=grandparent)
        parent_code, _ = ReferralCode.objects.get_or_create(user=parent)
        
        # Create existing referral relationships
        Referral.objects.create(
            referrer=grandparent,
            referred=parent,
            level=1,
            referral_code=grandparent_code
        )
        Referral.objects.create(
            referrer=parent,
            referred=self.referrer,
            level=1,
            referral_code=parent_code
        )
        
        # Now create multi-tier referrals for new user
        create_multi_tier_referrals(self.new_user, self.referrer)
        
        # Check level 2 referral (parent -> new_user)
        level2_referral = Referral.objects.get(
            referrer=parent,
            referred=self.new_user,
            level=2
        )
        self.assertEqual(level2_referral.referral_code, parent_code)
        
        # Check level 3 referral (grandparent -> new_user)
        level3_referral = Referral.objects.get(
            referrer=grandparent,
            referred=self.new_user,
            level=3
        )
        self.assertEqual(level3_referral.referral_code, grandparent_code)
    
    def test_create_multi_tier_referrals_partial_chain(self):
        """Test multi-tier creation with incomplete chain"""
        # Only create one level up
        parent = User.objects.create_user(
            username='parent',
            email='parent@example.com',
            password='testpass123'
        )
        parent_code, _ = ReferralCode.objects.get_or_create(user=parent)
        
        Referral.objects.create(
            referrer=parent,
            referred=self.referrer,
            level=1,
            referral_code=parent_code
        )
        
        create_multi_tier_referrals(self.new_user, self.referrer)
        
        # Should create level 2 only
        self.assertTrue(
            Referral.objects.filter(
                referrer=parent,
                referred=self.new_user,
                level=2
            ).exists()
        )
        
        # Should not create level 3
        self.assertFalse(
            Referral.objects.filter(
                referred=self.new_user,
                level=3
            ).exists()
        )
    
    def test_create_multi_tier_referrals_no_chain(self):
        """Test multi-tier creation when no upstream referrals exist"""
        create_multi_tier_referrals(self.new_user, self.referrer)
        
        # Should not create any additional referrals
        multi_tier_referrals = Referral.objects.filter(
            referred=self.new_user,
            level__gt=1
        )
        self.assertEqual(len(multi_tier_referrals), 0)
    
    def test_calculate_referral_commission_with_tiers(self):
        """Test commission calculation with commission tiers"""
        # Create commission tiers
        CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
        CommissionTier.objects.create(
            level=2,
            rate=Decimal('5.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        # Create referral relationships
        level1_referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.new_user,
            level=1,
            referral_code=self.referral_code
        )
        
        parent = User.objects.create_user(
            username='parent',
            email='parent@example.com',
            password='testpass123'
        )
        parent_code, _ = ReferralCode.objects.get_or_create(user=parent)
        level2_referral = Referral.objects.create(
            referrer=parent,
            referred=self.new_user,
            level=2,
            referral_code=parent_code
        )
        
        # Calculate commissions
        base_amount = Decimal('100.00')
        calculate_referral_commission(self.new_user, 'task_completion', base_amount)
        
        # Check earnings were created
        level1_earning = ReferralEarning.objects.get(
            referral=level1_referral,
            earning_type='task_completion'
        )
        level2_earning = ReferralEarning.objects.get(
            referral=level2_referral,
            earning_type='task_completion'
        )
        
        self.assertEqual(level1_earning.amount, Decimal('10.00'))  # 10% of 100
        self.assertEqual(level1_earning.commission_rate, Decimal('10.00'))
        self.assertEqual(level2_earning.amount, Decimal('5.00'))   # 5% of 100
        self.assertEqual(level2_earning.commission_rate, Decimal('5.00'))
    
    def test_calculate_referral_commission_no_tiers(self):
        """Test commission calculation when no tiers exist"""
        Referral.objects.create(
            referrer=self.referrer,
            referred=self.new_user,
            level=1,
            referral_code=self.referral_code
        )
        
        calculate_referral_commission(self.new_user, 'task_completion', Decimal('100.00'))
        
        # No earnings should be created
        self.assertEqual(
            ReferralEarning.objects.filter(referred_user=self.new_user).count(),
            0
        )
    
    def test_calculate_referral_commission_inactive_tiers(self):
        """Test commission calculation with inactive tiers"""
        CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=False  # Inactive tier
        )
        
        Referral.objects.create(
            referrer=self.referrer,
            referred=self.new_user,
            level=1,
            referral_code=self.referral_code
        )
        
        calculate_referral_commission(self.new_user, 'task_completion', Decimal('100.00'))
        
        # No earnings should be created for inactive tiers
        self.assertEqual(
            ReferralEarning.objects.filter(referred_user=self.new_user).count(),
            0
        )
    
    def test_get_referral_stats_comprehensive(self):
        """Test comprehensive referral statistics calculation"""
        # Create additional users and referrals
        users = []
        for i in range(3):
            user = User.objects.create_user(
                username=f'user_{i}',
                email=f'user_{i}@example.com',
                password='testpass123'
            )
            users.append(user)
            
            # Create direct referral
            Referral.objects.get_or_create(
                referrer=self.referrer,
                referred=user,
                level=1,
                referral_code=self.referral_code
            )
            
            # Create indirect referral
            if i > 0:
                Referral.objects.get_or_create(
                    referrer=self.referrer,
                    referred=user,
                    level=2,
                    referral_code=self.referral_code
                )
        
        # Create earnings with different statuses
        ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=users[0],
            referral=Referral.objects.get(referrer=self.referrer, referred=users[0], level=1),
            amount=Decimal('50.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )
        ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=users[1],
            referral=Referral.objects.get(referrer=self.referrer, referred=users[1], level=1),
            amount=Decimal('30.00'),
            earning_type='signup',
            commission_rate=Decimal('0.00'),
            status='paid'
        )
        ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=users[2],
            referral=Referral.objects.get(referrer=self.referrer, referred=users[2], level=1),
            amount=Decimal('20.00'),
            earning_type='advertiser_funding',
            commission_rate=Decimal('2.00'),
            status='pending'
        )
        
        stats = get_referral_stats(self.referrer)
        
        self.assertEqual(stats['total_referrals'], 5)  # 3 level 1 + 2 level 2
        self.assertEqual(stats['direct_referrals'], 3)
        self.assertEqual(stats['indirect_referrals'], 2)
        self.assertEqual(stats['total_earnings'], Decimal('80.00'))  # approved + paid
        self.assertEqual(stats['pending_earnings'], Decimal('20.00'))
        self.assertEqual(stats['paid_earnings'], Decimal('30.00'))
    
    def test_get_referral_stats_empty(self):
        """Test referral statistics for user with no referrals"""
        empty_user = User.objects.create_user(
            username='empty',
            email='empty@example.com',
            password='testpass123'
        )
        
        stats = get_referral_stats(empty_user)
        
        self.assertEqual(stats['total_referrals'], 0)
        self.assertEqual(stats['direct_referrals'], 0)
        self.assertEqual(stats['indirect_referrals'], 0)
        self.assertEqual(stats['total_earnings'], Decimal('0'))
        self.assertEqual(stats['pending_earnings'], Decimal('0'))
        self.assertEqual(stats['paid_earnings'], Decimal('0'))

