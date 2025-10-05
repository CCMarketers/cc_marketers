
# tests/test_signals.py
from django.test import TestCase
from django.contrib.auth import get_user_model

from decimal import Decimal

from referrals.models import ReferralCode, Referral, ReferralEarning, CommissionTier
from referrals.signals import create_referral_earning
from referrals.services import credit_signup_bonus_on_subscription

User = get_user_model()


class SignalsTests(TestCase):
    """Test cases for signal handlers"""
    
    def test_create_referral_code_signal(self):
        """Test that referral code is created when user is created"""
        user = User.objects.create_user(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        
        # Signal should have created referral code
        self.assertTrue(
            ReferralCode.objects.filter(user=user).exists()
        )
        
        code = ReferralCode.objects.get(user=user)
        self.assertTrue(code.is_active)
        self.assertEqual(len(code.code), 8)
    
    def test_create_referral_code_signal_not_triggered_on_update(self):
        """Test that referral code is not created on user update"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        initial_count = ReferralCode.objects.count()
        
        # Update user
        user.email = 'updated@example.com'
        user.save()
        
        # Should not create another referral code
        self.assertEqual(ReferralCode.objects.count(), initial_count)
    
    def test_handle_user_signup_with_referral_code(self):
        """Test user signup handling with referral code"""
        # Create referrer
        referrer = User.objects.create_user(
            username='referrer',
            email='referrer@example.com',
            password='testpass123'
        )
        referrer_code = ReferralCode.objects.get(user=referrer)
        
        # Create new user with referral code
        new_user = User(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        new_user.used_referral_code_id = referrer_code.id
        new_user.save()
        
        # Should create level 1 referral
        referral = Referral.objects.get(
            referrer=referrer,
            referred=new_user,
            level=1
        )
        self.assertEqual(referral.referral_code, referrer_code)
    
    def test_handle_user_signup_multi_tier_creation(self):
        """Test multi-tier referral creation on signup"""
        # Create referral chain
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
        direct_referrer = User.objects.create_user(
            username='direct',
            email='direct@example.com',
            password='testpass123'
        )
        
        grandparent_code = ReferralCode.objects.get(user=grandparent)
        parent_code = ReferralCode.objects.get(user=parent)
        direct_code = ReferralCode.objects.get(user=direct_referrer)
        
        # Create referral relationships
        Referral.objects.create(
            referrer=grandparent,
            referred=parent,
            level=1,
            referral_code=grandparent_code
        )
        Referral.objects.create(
            referrer=parent,
            referred=direct_referrer,
            level=1,
            referral_code=parent_code
        )
        
        # Create new user
        new_user = User(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        new_user.used_referral_code_id = direct_code.id
        new_user.save()
        
        # Should create all three levels
        self.assertTrue(
            Referral.objects.filter(
                referrer=direct_referrer,
                referred=new_user,
                level=1
            ).exists()
        )
        self.assertTrue(
            Referral.objects.filter(
                referrer=parent,
                referred=new_user,
                level=2
            ).exists()
        )
        self.assertTrue(
            Referral.objects.filter(
                referrer=grandparent,
                referred=new_user,
                level=3
            ).exists()
        )
    
    def test_handle_user_signup_invalid_referral_code(self):
        """Test user signup with invalid referral code"""
        new_user = User(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        new_user.used_referral_code_id = 99999  # Non-existent ID
        new_user.save()
        
        # Should not create any referrals
        self.assertEqual(
            Referral.objects.filter(referred=new_user).count(),
            0
        )
    
    def test_handle_user_signup_inactive_referral_code(self):
        """Test user signup with inactive referral code"""
        referrer = User.objects.create_user(
            username='referrer',
            email='referrer@example.com',
            password='testpass123'
        )
        referrer_code = ReferralCode.objects.get(user=referrer)
        referrer_code.is_active = False
        referrer_code.save()
        
        new_user = User(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        new_user.used_referral_code_id = referrer_code.id
        new_user.save()
        
        # Should not create referral for inactive code
        self.assertEqual(
            Referral.objects.filter(referred=new_user).count(),
            0
        )
    
    def test_create_referral_earning_function(self):
        """Test create_referral_earning function"""
        # Create users and relationships
        referrer = User.objects.create_user(
            username='referrer',
            email='referrer@example.com',
            password='testpass123'
        )
        referred = User.objects.create_user(
            username='referred',
            email='referred@example.com',
            password='testpass123'
        )
        
        referrer_code = ReferralCode.objects.get(user=referrer)
        Referral.objects.create(
            referrer=referrer,
            referred=referred,
            level=1,
            referral_code=referrer_code
        )
        
        # Create commission tier
        CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        # Call create_referral_earning
        base_amount = Decimal('100.00')
        create_referral_earning(referred, 'task_completion', base_amount)
        
        # Should create earning
        earning = ReferralEarning.objects.get(
            referrer=referrer,
            referred_user=referred
        )
        
        self.assertEqual(earning.amount, Decimal('10.00'))  # 10% of 100
        self.assertEqual(earning.earning_type, 'task_completion')
        self.assertEqual(earning.commission_rate, Decimal('10.00'))
        self.assertEqual(earning.status, 'pending')


class ServicesTests(TestCase):
    """Test cases for service functions"""
    
    def setUp(self):
        self.referrer = User.objects.create_user(
            username='referrer',
            email='referrer@example.com',
            password='testpass123'
        )
        self.referred = User.objects.create_user(
            username='referred',
            email='referred@example.com',
            password='testpass123'
        )
        
        referrer_code = ReferralCode.objects.get(user=self.referrer)
        self.referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
            level=1,
            referral_code=referrer_code
        )
    
    def test_credit_signup_bonus_first_subscription(self):
        """Test signup bonus credit on first subscription"""
        credit_signup_bonus_on_subscription(self.referred)
        
        # Should create signup earning
        earning = ReferralEarning.objects.get(
            referrer=self.referrer,
            referred_user=self.referred,
            earning_type='signup'
        )
        
        self.assertEqual(earning.amount, Decimal('5.00'))
        self.assertEqual(earning.commission_rate, Decimal('0.00'))
        self.assertEqual(earning.status, 'approved')
        self.assertIsNotNone(earning.approved_at)
    
    def test_credit_signup_bonus_prevents_duplicate(self):
        """Test that signup bonus is only credited once"""
        # Credit first time
        credit_signup_bonus_on_subscription(self.referred)
        
        initial_count = ReferralEarning.objects.filter(
            referred_user=self.referred,
            earning_type='signup'
        ).count()
        
        # Try to credit again
        credit_signup_bonus_on_subscription(self.referred)
        
        # Should not create duplicate
        final_count = ReferralEarning.objects.filter(
            referred_user=self.referred,
            earning_type='signup'
        ).count()
        
        self.assertEqual(initial_count, final_count)
    
    def test_credit_signup_bonus_no_referral(self):
        """Test signup bonus when user has no referral"""
        user_no_referral = User.objects.create_user(
            username='noreferral',
            email='noreferral@example.com',
            password='testpass123'
        )
        
        credit_signup_bonus_on_subscription(user_no_referral)
        
        # Should not create any earnings
        self.assertEqual(
            ReferralEarning.objects.filter(referred_user=user_no_referral).count(),
            0
        )
    
    def test_credit_signup_bonus_inactive_referral(self):
        """Test signup bonus with inactive referral"""
        self.referral.is_active = False
        self.referral.save()
        
        credit_signup_bonus_on_subscription(self.referred)
        
        # Should not create earning for inactive referral
        self.assertEqual(
            ReferralEarning.objects.filter(
                referred_user=self.referred,
                earning_type='signup'
            ).count(),
            0
        )
