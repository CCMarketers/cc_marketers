"""
Integration tests to ensure all components work together
"""
from decimal import Decimal
from django.test import  TransactionTestCase
from django.contrib.auth import get_user_model

from referrals.models import ReferralCode, Referral, ReferralEarning, CommissionTier
from referrals.signals import create_referral_earning
from referrals.services import credit_signup_bonus_on_subscription
from referrals.utils import  get_referral_stats
from wallets.models import Wallet

User = get_user_model()


class ReferralSystemIntegrationTests(TransactionTestCase):
    """Full integration tests for the referral system"""
    
    def setUp(self):
        """Set up a complete referral chain for testing"""
        # Create users in referral chain
        self.grandparent = User.objects.create_user(
            username='grandparent',
            email='grandparent@example.com',
            password='testpass123'
        )
        self.parent = User.objects.create_user(
            username='parent',
            email='parent@example.com',
            password='testpass123'
        )
        self.direct_referrer = User.objects.create_user(
            username='direct',
            email='direct@example.com',
            password='testpass123'
        )
        
        # Create referral relationships
        grandparent_code = ReferralCode.objects.get(user=self.grandparent)
        parent_code = ReferralCode.objects.get(user=self.parent)
        ReferralCode.objects.get(user=self.direct_referrer)
        
        Referral.objects.create(
            referrer=self.grandparent,
            referred=self.parent,
            level=1,
            referral_code=grandparent_code
        )
        Referral.objects.create(
            referrer=self.parent,
            referred=self.direct_referrer,
            level=1,
            referral_code=parent_code
        )
        
        # Create commission tiers for all levels and types
        commission_data = [
            (1, 'signup', Decimal('5.00')),
            (1, 'task_completion', Decimal('10.00')),
            (1, 'advertiser_funding', Decimal('2.00')),
            (2, 'task_completion', Decimal('5.00')),
            (2, 'advertiser_funding', Decimal('1.00')),
            (3, 'task_completion', Decimal('2.50')),
        ]
        
        for level, earning_type, rate in commission_data:
            CommissionTier.objects.create(
                level=level,
                rate=rate,
                earning_type=earning_type,
                is_active=True
            )

    def test_complete_referral_flow(self):
        """Test complete referral flow from signup to earnings"""
        # Step 1: New user signs up with referral code
        direct_code = ReferralCode.objects.get(user=self.direct_referrer)
        
        new_user = User(
            username='newuser',
            email='newuser@example.com',
            password='testpass123'
        )
        new_user.used_referral_code_id = direct_code.id
        new_user.save()
        
        # Verify referral relationships were created
        referrals = Referral.objects.filter(referred=new_user).order_by('level')
        self.assertEqual(len(referrals), 3)
        
        # Level 1: Direct referrer -> new user
        self.assertEqual(referrals[0].referrer, self.direct_referrer)
        self.assertEqual(referrals[0].level, 1)
        
        # Level 2: Parent -> new user
        self.assertEqual(referrals[1].referrer, self.parent)
        self.assertEqual(referrals[1].level, 2)
        
        # Level 3: Grandparent -> new user
        self.assertEqual(referrals[2].referrer, self.grandparent)
        self.assertEqual(referrals[2].level, 3)
        
        # Step 2: User subscribes (triggers signup bonus)
        credit_signup_bonus_on_subscription(new_user)
        
        # Verify signup bonus was credited to direct referrer only
        signup_earnings = ReferralEarning.objects.filter(
            referred_user=new_user,
            earning_type='signup'
        )
        self.assertEqual(len(signup_earnings), 1)
        self.assertEqual(signup_earnings[0].referrer, self.direct_referrer)
        self.assertEqual(signup_earnings[0].amount, Decimal('5.00'))
        
        # Step 3: User completes tasks (triggers multi-level commissions)
        create_referral_earning(new_user, 'task_completion', Decimal('100.00'))
        ReferralEarning.objects.filter(
            referred_user=new_user,
            earning_type='task_completion'
        ).update(status='approved')
        
        # Verify task completion earnings for all levels
        task_earnings = ReferralEarning.objects.filter(
            referred_user=new_user,
            earning_type='task_completion'
        ).order_by('referral__level')
        
        self.assertEqual(len(task_earnings), 3)
        self.assertEqual(task_earnings[0].referrer, self.direct_referrer)
        self.assertEqual(task_earnings[0].amount, Decimal('10.00'))  # 10%
        self.assertEqual(task_earnings[1].referrer, self.parent)
        self.assertEqual(task_earnings[1].amount, Decimal('5.00'))   # 5%
        self.assertEqual(task_earnings[2].referrer, self.grandparent)
        self.assertEqual(task_earnings[2].amount, Decimal('2.50'))   # 2.5%
        
        # Step 4: Advertiser funds account
        create_referral_earning(new_user, 'advertiser_funding', Decimal('1000.00'))
        ReferralEarning.objects.filter(
            referred_user=new_user,
            earning_type='advertiser_funding'
        ).update(status='approved')
        
        # Verify advertiser funding earnings
        funding_earnings = ReferralEarning.objects.filter(
            referred_user=new_user,
            earning_type='advertiser_funding'
        ).order_by('referral__level')
        
        self.assertEqual(len(funding_earnings), 2)  # Only levels 1 and 2 have tiers
        self.assertEqual(funding_earnings[0].amount, Decimal('20.00'))  # 2%
        self.assertEqual(funding_earnings[1].amount, Decimal('10.00'))  # 1%
        
        # Step 5: Verify total stats for each referrer
        direct_stats = get_referral_stats(self.direct_referrer)
        parent_stats = get_referral_stats(self.parent)
        grandparent_stats = get_referral_stats(self.grandparent)
        
        # Direct referrer should have all three earning types
        self.assertEqual(direct_stats['total_earnings'], Decimal('35.00'))  # 5+10+20
        
        # Parent should have task and funding earnings
        self.assertEqual(parent_stats['total_earnings'], Decimal('15.00'))  # 5+10
        
        # Grandparent should only have task earnings
        self.assertEqual(grandparent_stats['total_earnings'], Decimal('2.50'))  # 2.50



    def test_wallet_integration(self):
        """Test integration with wallet system"""
        # Create new user and referral
        direct_code = ReferralCode.objects.get(user=self.direct_referrer)
        new_user = User(
            username='walletuser',
            email='wallet@example.com',
            password='testpass123'
        )
        new_user.used_referral_code_id = direct_code.id
        new_user.save()
        
        # Create wallet for direct referrer
        wallet = Wallet.objects.create(
            user=self.direct_referrer,
            balance=Decimal('100.00')
        )
        
        initial_balance = wallet.balance
        
        # Credit signup bonus (should auto-credit to wallet)
        credit_signup_bonus_on_subscription(new_user)
        
        # Verify wallet was credited
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, initial_balance + Decimal('5.00'))
        
        # Verify transaction was created
        from wallets.models import Transaction
        transaction = Transaction.objects.get(
            user=self.direct_referrer,
            category='referral_bonus'
        )
        self.assertEqual(transaction.amount, Decimal('5.00'))
        self.assertEqual(transaction.transaction_type, 'credit')
    
    def test_error_handling_in_integration(self):
        """Test error handling throughout the integration"""
        # Test with invalid referral code
        invalid_user = User(
            username='invalid',
            email='invalid@example.com',
            password='testpass123'
        )
        invalid_user.used_referral_code_id = 99999
        invalid_user.save()
        
        # Should not create any referrals or break anything
        self.assertEqual(
            Referral.objects.filter(referred=invalid_user).count(),
            0
        )
        
        # Test duplicate signup bonus
        direct_code = ReferralCode.objects.get(user=self.direct_referrer)
        duplicate_user = User(
            username='duplicate',
            email='duplicate@example.com',
            password='testpass123'
        )
        duplicate_user.used_referral_code_id = direct_code.id
        duplicate_user.save()
        
        # Credit signup bonus twice
        credit_signup_bonus_on_subscription(duplicate_user)
        credit_signup_bonus_on_subscription(duplicate_user)
        
        # Should only have one signup earning
        signup_earnings = ReferralEarning.objects.filter(
            referred_user=duplicate_user,
            earning_type='signup'
        )
        self.assertEqual(len(signup_earnings), 1)
    
    def test_concurrent_operations(self):
        """Test concurrent operations don't cause issues"""
        direct_code = ReferralCode.objects.get(user=self.direct_referrer)
        
        # Create multiple users concurrently with same referrer
        users = []
        for i in range(5):
            user = User(
                username=f'concurrent_{i}',
                email=f'concurrent_{i}@example.com',
                password='testpass123'
            )
            user.used_referral_code_id = direct_code.id
            user.save()
            users.append(user)
        
        # Generate earnings for all users
        for user in users:
            credit_signup_bonus_on_subscription(user)
            create_referral_earning(user, 'task_completion', Decimal('50.00'))
        
        # Verify all earnings were created correctly
        total_signup_earnings = ReferralEarning.objects.filter(
            referrer=self.direct_referrer,
            earning_type='signup'
        ).count()
        self.assertEqual(total_signup_earnings, 5)
        
        total_task_earnings = ReferralEarning.objects.filter(
            referrer=self.direct_referrer,
            earning_type='task_completion'
        ).count()
        self.assertEqual(total_task_earnings, 5)

