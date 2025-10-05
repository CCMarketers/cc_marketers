# tests/test_models.py
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone
from unittest.mock import patch, Mock

from referrals.models import ReferralCode, Referral, ReferralEarning, CommissionTier
from wallets.models import Wallet, Transaction

User = get_user_model()


class ReferralCodeModelTests(TestCase):
    """Test cases for ReferralCode model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_referral_code_creation(self):
        """Test basic referral code creation"""
        code, _ = ReferralCode.objects.get_or_create(user=self.user)
        
        self.assertEqual(code.user, self.user)
        self.assertTrue(code.is_active)
        self.assertIsNotNone(code.created_at)
        self.assertEqual(len(code.code), 8)
    
    def test_referral_code_auto_generation(self):
        """Test that referral code is auto-generated if not provided"""
        code, _ = ReferralCode.objects.get_or_create(user=self.user)
        
        self.assertIsNotNone(code.code)
        self.assertEqual(len(code.code), 8)
        
        # Code should contain only uppercase letters and digits
        import string
        allowed_chars = string.ascii_uppercase + string.digits
        for char in code.code:
            self.assertIn(char, allowed_chars)


    def test_referral_code_uniqueness(self):
        """Test that referral codes are unique"""
        with patch.object(ReferralCode, 'generate_code') as mock_generate:
            # First call returns duplicate, second returns unique
            mock_generate.side_effect = ['DUPLICATECODE', 'UNIQUECODE']

            # Create first code
            referralcode, _ = ReferralCode.objects.get_or_create(user=self.user)

            # Create second user and code
            user2 = User.objects.create_user(
                username='user2',
                email='user2@example.com',
                password='testpass123'
            )
            code2, _ = ReferralCode.objects.get_or_create(user=user2)

            # Should have generated unique code
            self.assertNotEqual(code2.code, referralcode.code)



    def test_referral_code_string_representation(self):
        """Test string representation of referral code"""
        code, _ = ReferralCode.objects.get_or_create(user=self.user, )
        expected = f"{self.user} - {code.code}"
        self.assertEqual(str(code), expected)
    
    def test_referral_code_unique_constraint(self):
        """Test that duplicate codes raise IntegrityError"""
        ReferralCode.objects.get_or_create(user=self.user)
        
        user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        with self.assertRaises(IntegrityError):
            ReferralCode.objects.get_or_create(user=user2, code='DUPLICATE')


class ReferralModelTests(TestCase):
    """Test cases for Referral model"""
    
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
        self.referral_code, _ = ReferralCode.objects.get_or_create(
            user=self.referrer,
        )
    
    def test_referral_creation(self):
        """Test basic referral creation"""
        referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
            level=1,
            referral_code=self.referral_code
        )
        
        self.assertEqual(referral.referrer, self.referrer)
        self.assertEqual(referral.referred, self.referred)
        self.assertEqual(referral.level, 1)
        self.assertTrue(referral.is_active)
        self.assertIsNotNone(referral.created_at)
    
    def test_referral_level_choices(self):
        """Test that referral levels are properly set"""
        levels = [1, 2, 3]
        
        for level in levels:
            user = User.objects.create_user(
                username=f'user_level_{level}',
                email=f'level_{level}@example.com',
                password='testpass123'
            )
            referral = Referral.objects.create(
                referrer=self.referrer,
                referred=user,
                level=level,
                referral_code=self.referral_code
            )
            self.assertEqual(referral.level, level)
    
    def test_referral_string_representation(self):
        """Test string representation of referral"""
        referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
            level=1,
            referral_code=self.referral_code
        )
        
        expected = f"{self.referrer} → {self.referred} (Level 1)"
        self.assertEqual(str(referral), expected)
    
    def test_referral_unique_together_constraint(self):
        """Test that referrer-referred pairs must be unique"""
        # Create first referral
        Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
            level=1,
            referral_code=self.referral_code
        )
        
        # Try to create duplicate
        with self.assertRaises(IntegrityError):
            Referral.objects.create(
                referrer=self.referrer,
                referred=self.referred,
                level=1,
                referral_code=self.referral_code
            )
    
    def test_referral_default_values(self):
        """Test default values for referral fields"""
        referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
            referral_code=self.referral_code
        )
        
        # Default level should be 1
        self.assertEqual(referral.level, 1)
        # Default is_active should be True
        self.assertTrue(referral.is_active)


class ReferralEarningModelTests(TestCase):
    """Test cases for ReferralEarning model"""
    
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
        self.referral_code, _ = ReferralCode.objects.get_or_create(
            user=self.referrer,
        )
        self.referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
            level=1,
            referral_code=self.referral_code
        )
        
        # Create wallet for referrer
        self.wallet = Wallet.objects.create(
            user=self.referrer,
            balance=Decimal('100.00')
        )
    
    def test_referral_earning_creation(self):
        """Test basic referral earning creation"""
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )
        
        self.assertEqual(earning.referrer, self.referrer)
        self.assertEqual(earning.referred_user, self.referred)
        self.assertEqual(earning.referral, self.referral)
        self.assertEqual(earning.amount, Decimal('25.00'))
        self.assertEqual(earning.earning_type, 'task_completion')
        self.assertEqual(earning.commission_rate, Decimal('10.00'))
        self.assertEqual(earning.status, 'approved')
        self.assertIsNotNone(earning.created_at)
    
    def test_referral_earning_default_status(self):
        """Test that default status is 'approved'"""
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='signup',
            commission_rate=Decimal('0.00')
        )
        
        self.assertEqual(earning.status, 'approved')
    
    @patch('referrals.models.Transaction.objects.create')
    @patch('referrals.models.Wallet.objects.get_or_create')
    def test_referral_earning_auto_credit_on_creation(self, mock_wallet_get_create, mock_transaction_create):
        """Test that approved earnings are auto-credited on creation"""
        # Mock wallet get_or_create
        mock_wallet_get_create.return_value = (self.wallet, False)
        
        # Mock transaction creation
        mock_transaction = Mock()
        mock_transaction.id = 123
        mock_transaction_create.return_value = mock_transaction
        
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )
        
        # Should have auto-set approved timestamp
        self.assertIsNotNone(earning.approved_at)
        
        # Should have called credit_wallet (which calls Transaction.objects.create)
        mock_transaction_create.assert_called_once()
    
    def test_referral_earning_credit_wallet_functionality(self):
        """Test wallet crediting functionality"""
        initial_balance = self.wallet.balance
        
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('50.00'),
            earning_type='advertiser_funding',
            commission_rate=Decimal('2.00'),
            status='approved'
        )
        
        # Check that transaction was created
        transaction = Transaction.objects.get(reference=f"REFERRAL_{earning.id}")
        self.assertEqual(transaction.user, self.referrer)
        self.assertEqual(transaction.amount, Decimal('50.00'))
        self.assertEqual(transaction.transaction_type, 'credit')
        self.assertEqual(transaction.category, 'referral_bonus')
        self.assertEqual(transaction.status, 'success')
        
        # Check wallet balance updated
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, initial_balance + Decimal('50.00'))
        
        # Check transaction reference saved
        self.assertEqual(earning.transaction_id, str(transaction.id))

    def test_referral_earning_prevent_duplicate_crediting(self):
        """Test that duplicate crediting is prevented"""
        # Create initial earning
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )

        # Refresh wallet after first auto-credit
        self.wallet.refresh_from_db()
        initial_balance = self.wallet.balance
        initial_transaction_count = Transaction.objects.count()

        # Call credit_wallet again
        earning.credit_wallet()

        # Should not create duplicate transaction
        self.assertEqual(Transaction.objects.count(), initial_transaction_count)

        # Wallet balance should not change
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, initial_balance)




    def test_referral_earning_approve_method(self):
        """Test the approve method functionality"""
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('30.00'),
            earning_type='subscription',
            commission_rate=Decimal('15.00'),
            status='pending'
        )
        
        # Initially should be pending with no approved_at
        self.assertEqual(earning.status, 'pending')
        self.assertIsNone(earning.approved_at)
        
        # Approve the earning
        earning.approve()
        
        # Should now be approved with timestamp
        earning.refresh_from_db()
        self.assertEqual(earning.status, 'approved')
        self.assertIsNotNone(earning.approved_at)
    
    def test_referral_earning_choices_validation(self):
        """Test that earning type and status choices are properly validated"""
        valid_earning_types = ['signup', 'task_completion', 'advertiser_funding', 'subscription']
        valid_statuses = ['pending', 'approved', 'paid', 'cancelled']
        
        for earning_type in valid_earning_types:
            earning = ReferralEarning.objects.create(
                referrer=self.referrer,
                referred_user=self.referred,
                referral=self.referral,
                amount=Decimal('10.00'),
                earning_type=earning_type,
                commission_rate=Decimal('5.00'),
                status='pending'
            )
            self.assertEqual(earning.earning_type, earning_type)
        
        for status in valid_statuses:
            earning = ReferralEarning.objects.create(
                referrer=self.referrer,
                referred_user=self.referred,
                referral=self.referral,
                amount=Decimal('10.00'),
                earning_type='signup',
                commission_rate=Decimal('0.00'),
                status=status
            )
            self.assertEqual(earning.status, status)
    
    def test_referral_earning_decimal_precision(self):
        """Test decimal field precision and rounding"""
        # Test maximum precision
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('99999999.99'),
            earning_type='advertiser_funding',
            commission_rate=Decimal('999.99'),
            status='approved'
        )
        
        self.assertEqual(earning.amount, Decimal('99999999.99'))
        self.assertEqual(earning.commission_rate, Decimal('999.99'))
    
    def test_referral_earning_timestamp_behavior(self):
        """Test timestamp field behavior"""
        earning = ReferralEarning.objects.create(
            referrer=self.referrer,
            referred_user=self.referred,
            referral=self.referral,
            amount=Decimal('15.00'),
            earning_type='signup',
            commission_rate=Decimal('0.00'),
            status='pending'
        )
        
        # Should have created_at but not approved_at or paid_at
        self.assertIsNotNone(earning.created_at)
        self.assertIsNone(earning.approved_at)
        self.assertIsNone(earning.paid_at)
        
        # Approve it
        earning.status = 'approved'
        earning.approved_at = timezone.now()
        earning.save()
        
        self.assertIsNotNone(earning.approved_at)
        self.assertIsNone(earning.paid_at)
        
        # Mark as paid
        earning.status = 'paid'
        earning.paid_at = timezone.now()
        earning.save()
        
        self.assertIsNotNone(earning.paid_at)


class CommissionTierModelTests(TestCase):
    """Test cases for CommissionTier model"""
    
    def test_commission_tier_creation(self):
        """Test basic commission tier creation"""
        tier = CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        self.assertEqual(tier.level, 1)
        self.assertEqual(tier.rate, Decimal('10.00'))
        self.assertEqual(tier.earning_type, 'task_completion')
        self.assertTrue(tier.is_active)
        self.assertIsNotNone(tier.created_at)
    
    def test_commission_tier_string_representation(self):
        """Test string representation of commission tier"""
        tier = CommissionTier.objects.create(
            level=2,
            rate=Decimal('5.50'),
            earning_type='advertiser_funding',
            is_active=True
        )
        
        expected = "Level 2 - 5.50% for advertiser_funding"
        self.assertEqual(str(tier), expected)
    
    def test_commission_tier_unique_together_constraint(self):
        """Test unique constraint on level and earning_type"""
        # Create first tier
        CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        # Try to create duplicate
        with self.assertRaises(IntegrityError):
            CommissionTier.objects.create(
                level=1,
                rate=Decimal('15.00'),
                earning_type='task_completion',
                is_active=True
            )
    
    def test_commission_tier_different_levels_same_type(self):
        """Test that different levels can have same earning type"""
        tier1 = CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        tier2 = CommissionTier.objects.create(
            level=2,
            rate=Decimal('5.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        self.assertNotEqual(tier1, tier2)
        self.assertEqual(tier1.earning_type, tier2.earning_type)
    
    def test_commission_tier_same_level_different_types(self):
        """Test that same level can have different earning types"""
        tier1 = CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        tier2 = CommissionTier.objects.create(
            level=1,
            rate=Decimal('5.00'),
            earning_type='advertiser_funding',
            is_active=True
        )
        
        self.assertNotEqual(tier1, tier2)
        self.assertEqual(tier1.level, tier2.level)
    
    def test_commission_tier_rate_precision(self):
        """Test commission rate decimal precision"""
        tier = CommissionTier.objects.create(
            level=3,
            rate=Decimal('99.99'),
            earning_type='subscription',
            is_active=True
        )
        
        self.assertEqual(tier.rate, Decimal('99.99'))
    
    def test_commission_tier_earning_type_choices(self):
        """Test that all earning type choices work"""
        earning_types = ['signup', 'task_completion', 'advertiser_funding', 'subscription']
        
        for i, earning_type in enumerate(earning_types, 1):
            tier = CommissionTier.objects.create(
                level=i,
                rate=Decimal('10.00'),
                earning_type=earning_type,
                is_active=True
            )
            self.assertEqual(tier.earning_type, earning_type)
    
    def test_commission_tier_active_inactive_states(self):
        """Test active and inactive commission tiers"""
        active_tier = CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='signup',
            is_active=True
        )
        
        inactive_tier = CommissionTier.objects.create(
            level=2,
            rate=Decimal('5.00'),
            earning_type='signup',
            is_active=False
        )
        
        self.assertTrue(active_tier.is_active)
        self.assertFalse(inactive_tier.is_active)
        
        # Test queryset filtering
        active_tiers = CommissionTier.objects.filter(is_active=True)
        inactive_tiers = CommissionTier.objects.filter(is_active=False)
        
        self.assertIn(active_tier, active_tiers)
        self.assertNotIn(active_tier, inactive_tiers)
        self.assertIn(inactive_tier, inactive_tiers)
        self.assertNotIn(inactive_tier, active_tiers)


class ModelRelationshipTests(TestCase):
    """Test model relationships and foreign key constraints"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        self.referral_code, _ = ReferralCode.objects.get_or_create(user=self.user1)
        self.referral = Referral.objects.create(
            referrer=self.user1,
            referred=self.user2,
            level=1,
            referral_code=self.referral_code
        )
    
    def test_user_referral_code_relationship(self):
        """Test one-to-one relationship between User and ReferralCode"""
        # Access referral code from user
        self.assertEqual(self.user1.referral_code, self.referral_code)
        
        # Access user from referral code
        self.assertEqual(self.referral_code.user, self.user1)
    
    def test_user_referrals_made_relationship(self):
        """Test referrals_made reverse relationship"""
        referrals_made = self.user1.referrals_made.all()
        self.assertEqual(len(referrals_made), 1)
        self.assertEqual(referrals_made[0], self.referral)
    
    def test_user_referral_source_relationship(self):
        """Test referral_source reverse relationship"""
        referral_source = self.user2.referral_source.all()
        self.assertEqual(len(referral_source), 1)
        self.assertEqual(referral_source[0], self.referral)
    
    def test_referral_code_referral_relationship(self):
        """Test referral code to referral relationship"""
        referrals = self.referral_code.referral_set.all()
        self.assertEqual(len(referrals), 1)
        self.assertEqual(referrals[0], self.referral)
    
    def test_referral_earning_relationships(self):
        """Test referral earning relationships"""
        earning = ReferralEarning.objects.create(
            referrer=self.user1,
            referred_user=self.user2,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )
        
        # Test referrer relationship
        self.assertEqual(earning.referrer, self.user1)
        referrer_earnings = self.user1.referral_earnings.all()
        self.assertIn(earning, referrer_earnings)
        
        # Test referred_user relationship
        self.assertEqual(earning.referred_user, self.user2)
        generated_earnings = self.user2.earnings_generated.all()
        self.assertIn(earning, generated_earnings)
        
        # Test referral relationship
        self.assertEqual(earning.referral, self.referral)
        referral_earnings = self.referral.referralearning_set.all()
        self.assertIn(earning, referral_earnings)
    
    def test_cascade_deletion_behavior(self):
        """Test cascade deletion behavior"""
        ReferralEarning.objects.create(
            referrer=self.user1,
            referred_user=self.user2,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )
        
        # Delete user1 (referrer)
        user1_id = self.user1.id
        self.user1.delete()
        
        # Should cascade delete referral code, referral, and earning
        self.assertFalse(ReferralCode.objects.filter(user_id=user1_id).exists())
        self.assertFalse(Referral.objects.filter(referrer_id=user1_id).exists())
        self.assertFalse(ReferralEarning.objects.filter(referrer_id=user1_id).exists())


class ModelValidationTests(TestCase):
    """Test model validation and constraints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    # def test_referral_code_length_validation(self):
    #     """Test referral code length constraints"""
    #     # Test maximum length (should work)
    #     long_code = 'A' * 10
    #     code, _ = ReferralCode.objects.get_or_create(user=self.user)
    #     self.assertEqual(code.code, long_code)
    
    def test_referral_earning_amount_validation(self):
        """Test referral earning amount constraints"""
        referral_code, _ = ReferralCode.objects.get_or_create(user=self.user)
        user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        referral = Referral.objects.create(
            referrer=self.user,
            referred=user2,
            level=1,
            referral_code=referral_code
        )
        
        # Test negative amount (should work - might be refunds)
        earning = ReferralEarning.objects.create(
            referrer=self.user,
            referred_user=user2,
            referral=referral,
            amount=Decimal('-10.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )
        self.assertEqual(earning.amount, Decimal('-10.00'))
        
        # Test zero amount (should work)
        earning_zero = ReferralEarning.objects.create(
            referrer=self.user,
            referred_user=user2,
            referral=referral,
            amount=Decimal('0.00'),
            earning_type='signup',
            commission_rate=Decimal('0.00'),
            status='approved'
        )
        self.assertEqual(earning_zero.amount, Decimal('0.00'))
    
    def test_commission_tier_rate_validation(self):
        """Test commission tier rate validation"""
        # Test zero rate (should work)
        tier_zero = CommissionTier.objects.create(
            level=1,
            rate=Decimal('0.00'),
            earning_type='signup',
            is_active=True
        )
        self.assertEqual(tier_zero.rate, Decimal('0.00'))
        
        # Test high rate (should work)
        tier_high = CommissionTier.objects.create(
            level=2,
            rate=Decimal('100.00'),
            earning_type='task_completion',
            is_active=True
        )
        self.assertEqual(tier_high.rate, Decimal('100.00'))


class ModelMethodTests(TestCase):
    """Test custom model methods"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_referral_code_generate_code_method(self):
        """Test generate_code method creates unique codes"""
        code = ReferralCode()
        generated_code = code.generate_code()
        
        # Should be 8 characters
        self.assertEqual(len(generated_code), 8)
        
        # Should be uppercase alphanumeric
        import string
        allowed_chars = string.ascii_uppercase + string.digits
        for char in generated_code:
            self.assertIn(char, allowed_chars)
    
    @patch('referrals.models.ReferralCode.objects.filter')
    def test_referral_code_generate_unique_code(self, mock_filter):
        """Test that generate_code ensures uniqueness"""
        # Mock that first code exists, second doesn't
        mock_filter.side_effect = [
            Mock(exists=Mock(return_value=True)),   # First code exists
            Mock(exists=Mock(return_value=False)),  # Second code is unique
        ]
        
        with patch('random.choices') as mock_choices:
            # Return specific sequences
            mock_choices.side_effect = [
                ['D', 'U', 'P', 'L', 'I', 'C', 'A', 'T'],  # First (duplicate)
                ['U', 'N', 'I', 'Q', 'U', 'E', '1', '2'],  # Second (unique)
            ]
            
            code = ReferralCode()
            generated = code.generate_code()
            
            self.assertEqual(generated, 'UNIQUE12')
            self.assertEqual(mock_choices.call_count, 2)
