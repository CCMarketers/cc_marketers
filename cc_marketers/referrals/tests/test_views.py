# tests/test_views.py
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from subscriptions.models import  SubscriptionPlan, UserSubscription

from referrals.models import (
    ReferralCode, Referral, ReferralEarning, CommissionTier
)

User = get_user_model()


class BaseTestCase(TestCase):
    """Base test case with common setup for all test classes"""
    
    def setUp(self):
        """Set up test data used across multiple test cases"""
        self.client = Client()
            # Example: Attach subscription for multiple test users
        plan = SubscriptionPlan.objects.first()
        if not plan:
            plan = SubscriptionPlan.objects.create(
                name="Business Member Plan",
                price=0,
                duration_days=30,
                business_volume=0,
                referral_commission=0,
                commission_to_tree=0,
                daily_ad_limit=100000,
            )

        
        # Create test users
        self.regular_user = self.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.referrer_user = self.create_user(
            username='referrer',
            email='referrer@example.com',
            password='testpass123'
        )
        self.staff_user = self.create_user(
            username='staff',
            email='staff@example.com',
            password='testpass123',
            is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='testpass123'
        )
        for user in [self.regular_user, self.referrer_user, self.staff_user, self.superuser]:
            UserSubscription.objects.create(
                user=user,
                plan=plan,
                expiry_date=timezone.now() + timezone.timedelta(days=plan.duration_days),
                status="active"
            )
        # Create referral codes
        self.regular_code,_ = ReferralCode.objects.get_or_create(
            user=self.regular_user,
        )
        self.referrer_code,_ = ReferralCode.objects.get_or_create(
            user=self.referrer_user,
        )
        
        # Create referral relationship
        self.referral = Referral.objects.create(
            referrer=self.referrer_user,
            referred=self.regular_user,
            level=1,
            referral_code=self.referrer_code
        )
        
        # Create commission tiers
        self.commission_tier_1 = CommissionTier.objects.create(
            level=1,
            rate=Decimal('10.00'),
            earning_type='task_completion',
            is_active=True
        )
        self.commission_tier_2 = CommissionTier.objects.create(
            level=2,
            rate=Decimal('5.00'),
            earning_type='task_completion',
            is_active=True
        )
        
        # Create sample earnings
        self.earning_1 = ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('25.00'),
            earning_type='task_completion',
            commission_rate=Decimal('10.00'),
            status='approved'
        )
        self.earning_2 = ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('15.00'),
            earning_type='signup',
            commission_rate=Decimal('0.00'),
            status='pending'
        )

    @classmethod
    def create_user(cls, username, email, role='member', is_subscribed=False, is_staff=False, **kwargs):
        # Create the user
        user = User.objects.create_user(
            username=username,
            email=email,
            is_staff=is_staff,
            **kwargs
        )
        user.role = role
        user.save()

        # Attach subscription if needed
        if is_subscribed:
            plan = SubscriptionPlan.objects.first()
            if not plan:
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
                expiry_date=timezone.now() + timezone.timedelta(days=plan.duration_days),
                status="active"
            )

        return user






class ReferralDashboardViewTests(BaseTestCase):
    """Test cases for ReferralDashboardView"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('referrals:dashboard')
    
    def test_dashboard_requires_login(self):
        """Test that dashboard requires user authentication"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    # def test_dashboard_creates_referral_code_if_not_exists(self):
    #     """Test that dashboard creates referral code if user doesn't have one"""
    #     # Create user without referral code
    #     user_without_code = self.create_user(
    #         username='nocode',
    #         email='nocode@example.com',
    #         password='testpass123'
    #     )
    #     self.client.force_login(user_without_code)
        
    #     # Verify no referral code exists
    #     self.assertFalse(
    #         ReferralCode.objects.filter(user=user_without_code).exists()
    #     )
        
    #     response = self.client.get(self.url)
    #     self.assertEqual(response.status_code, 200)
        
    #     # Verify referral code was created
    #     self.assertTrue(
    #         ReferralCode.objects.filter(user=user_without_code).exists()
    #     )
    #     referral_code = ReferralCode.objects.get(user=user_without_code)
    #     self.assertTrue(referral_code.is_active)
    
    def test_dashboard_uses_existing_referral_code(self):
        """Test that dashboard uses existing referral code"""
        self.client.force_login(self.regular_user)
        
        # Store original code
        original_code = self.regular_code.code
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Verify same code is used
        self.regular_code.refresh_from_db()
        self.assertEqual(self.regular_code.code, original_code)
    
    def test_dashboard_context_data(self):
        """Test that dashboard provides correct context data"""
        self.client.force_login(self.referrer_user)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        
        # Check referral code
        self.assertEqual(context['referral_code'], self.referrer_code)
        
        # Check referral link
        expected_link = f"http://testserver{reverse('users:register')}?ref={self.referrer_code.code}"
        self.assertEqual(context['referral_link'], expected_link)
        
        # Check stats
        self.assertEqual(context['total_referrals'], 1)
        self.assertEqual(context['total_earnings'], Decimal('25.00'))  # Only approved earnings
        self.assertEqual(context['pending_earnings'], Decimal('15.00'))
        
        # Check recent data
        self.assertEqual(len(context['recent_referrals']), 1)
        self.assertEqual(len(context['recent_earnings']), 2)
    
    def test_dashboard_stats_with_no_data(self):
        """Test dashboard stats when user has no referrals or earnings"""
        user_no_data = self.create_user(
            username='nodata',
            email='nodata@example.com',
            password='testpass123'
        )
        self.client.force_login(user_no_data)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        self.assertEqual(context['total_referrals'], 0)
        self.assertEqual(context['total_earnings'], 0)
        self.assertEqual(context['pending_earnings'], 0)
        self.assertEqual(len(context['recent_referrals']), 0)
        self.assertEqual(len(context['recent_earnings']), 0)
    
    def test_dashboard_with_multiple_earnings_statuses(self):
        """Test dashboard calculations with various earning statuses"""
        self.client.force_login(self.referrer_user)
        
        # Create additional earnings with different statuses
        ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('30.00'),
            earning_type='advertiser_funding',
            commission_rate=Decimal('2.00'),
            status='paid'
        )
        ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('20.00'),
            earning_type='subscription',
            commission_rate=Decimal('15.00'),
            status='cancelled'
        )
        
        response = self.client.get(self.url)
        context = response.context
        
        # Total earnings should include approved and paid (25 + 30 = 55)
        self.assertEqual(context['total_earnings'], Decimal('55.00'))
        # Pending should only include pending status (15.00)
        self.assertEqual(context['pending_earnings'], Decimal('15.00'))


class ReferralListViewTests(BaseTestCase):
    """Test cases for ReferralListView"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('referrals:referral_list')
    
    def test_referral_list_requires_login(self):
        """Test that referral list requires authentication"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    def test_referral_list_shows_user_referrals_only(self):
        """Test that referral list shows only current user's referrals"""
        # Create another user with referrals
        other_user = self.create_user(
            username='other',
            email='other@example.com',
            password='testpass123'
        )
        other_code,_ = ReferralCode.objects.get_or_create(user=other_user)
        Referral.objects.create(
            referrer=other_user,
            referred=self.regular_user,
            level=2,
            referral_code=other_code
        )
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['referrals']), 1)
        self.assertEqual(response.context['referrals'][0], self.referral)
    
    def test_referral_list_pagination(self):
        """Test referral list pagination functionality"""
        # Create additional referrals to test pagination
        for i in range(25):
            user = self.create_user(
                username=f'ref_user_{i}',
                email=f'ref_user_{i}@example.com',
                password='testpass123'
            )
            Referral.objects.create(
                referrer=self.referrer_user,
                referred=user,
                level=1,
                referral_code=self.referrer_code
            )
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['referrals']), 20)  # paginate_by = 20
        self.assertTrue(response.context['is_paginated'])
    
    def test_referral_list_ordering(self):
        """Test that referrals are ordered by creation date descending"""
        # Create referral with specific creation time
        older_user = self.create_user(
            username='older',
            email='older@example.com',
            password='testpass123'
        )
        older_referral = Referral.objects.create(
            referrer=self.referrer_user,
            referred=older_user,
            level=1,
            referral_code=self.referrer_code
        )
        # Manually set older creation time
        older_referral.created_at = timezone.now() - timedelta(days=1)
        older_referral.save()
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(self.url)
        
        referrals = response.context['referrals']
        self.assertEqual(len(referrals), 2)
        # Most recent should be first
        self.assertEqual(referrals[0], self.referral)
        self.assertEqual(referrals[1], older_referral)
    
    def test_referral_list_empty_state(self):
        """Test referral list when user has no referrals"""
        user_no_refs = self.create_user(
            username='norefs',
            email='norefs@example.com',
            password='testpass123'
        )
        self.client.force_login(user_no_refs)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['referrals']), 0)


class EarningsListViewTests(BaseTestCase):
    """Test cases for EarningsListView"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('referrals:earnings_list')
    
    def test_earnings_list_requires_login(self):
        """Test that earnings list requires authentication"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    def test_earnings_list_shows_user_earnings_only(self):
        """Test that earnings list shows only current user's earnings"""
        # Create earning for another user
        other_user = self.create_user(
            username='other',
            email='other@example.com',
            password='testpass123'
        )
        other_referral = Referral.objects.create(
            referrer=other_user,
            referred=self.regular_user,
            level=2,
            referral_code=self.regular_code
        )
        ReferralEarning.objects.create(
            referrer=other_user,
            referred_user=self.regular_user,
            referral=other_referral,
            amount=Decimal('10.00'),
            earning_type='signup',
            commission_rate=Decimal('0.00'),
            status='approved'
        )
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['earnings']), 2)  # Only referrer_user's earnings
    
    def test_earnings_list_context_data(self):
        """Test that earnings list provides correct summary context"""
        self.client.force_login(self.referrer_user)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        summary = response.context['earnings_summary']
        self.assertEqual(summary['total'], Decimal('25.00'))  # Only approved/paid
        self.assertEqual(summary['pending'], Decimal('15.00'))
        self.assertEqual(summary['paid'], Decimal('0.00'))
    
    def test_earnings_list_summary_with_various_statuses(self):
        """Test earnings summary calculation with different statuses"""
        # Add earnings with different statuses
        ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('40.00'),
            earning_type='advertiser_funding',
            commission_rate=Decimal('2.00'),
            status='paid'
        )
        ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('50.00'),
            earning_type='subscription',
            commission_rate=Decimal('20.00'),
            status='cancelled'
        )
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(self.url)
        
        summary = response.context['earnings_summary']
        self.assertEqual(summary['total'], Decimal('65.00'))  # approved + paid (25 + 40)
        self.assertEqual(summary['pending'], Decimal('15.00'))
        self.assertEqual(summary['paid'], Decimal('40.00'))
    
    def test_earnings_list_pagination(self):
        """Test earnings list pagination"""
        # Create additional earnings
        for i in range(25):
            ReferralEarning.objects.create(
                referrer=self.referrer_user,
                referred_user=self.regular_user,
                referral=self.referral,
                amount=Decimal(f'{i + 1}.00'),
                earning_type='task_completion',
                commission_rate=Decimal('10.00'),
                status='approved'
            )
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['earnings']), 20)  # paginate_by = 20
        self.assertTrue(response.context['is_paginated'])
    
    def test_earnings_list_ordering(self):
        """Test that earnings are ordered by creation date descending"""
        # Create earning with older timestamp
        older_earning = ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('100.00'),
            earning_type='subscription',
            commission_rate=Decimal('15.00'),
            status='approved'
        )
        older_earning.created_at = timezone.now() - timedelta(days=2)
        older_earning.save()
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(self.url)
        
        earnings = list(response.context['earnings'])
        # Most recent should be first (earning_2 was created last in setUp)
        self.assertEqual(earnings[0], self.earning_2)


class CommissionTiersViewTests(BaseTestCase):
    """Test cases for CommissionTiersView"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('referrals:commission_tiers')
    
    def test_commission_tiers_accessible_without_login(self):
        """Test that commission tiers page is publicly accessible"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
    
    def test_commission_tiers_shows_active_tiers_only(self):
        """Test that only active commission tiers are displayed"""
        # Create inactive tier
        CommissionTier.objects.create(
            level=1,
            rate=Decimal('20.00'),
            earning_type='signup',
            is_active=False
        )
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Should only show active tiers
        active_tiers = [tier for tier in response.context['commission_tiers'] if tier.is_active]
        self.assertEqual(len(active_tiers), len(response.context['commission_tiers']))
    
    def test_commission_tiers_ordering(self):
        """Test that commission tiers are properly ordered"""
        # Create additional tiers
        CommissionTier.objects.create(
            level=3,
            rate=Decimal('2.00'),
            earning_type='task_completion',
            is_active=True
        )
        CommissionTier.objects.create(
            level=1,
            rate=Decimal('5.00'),
            earning_type='signup',
            is_active=True
        )
        
        response = self.client.get(self.url)
        tiers = response.context['commission_tiers']
        
        # Check ordering: level first, then earning_type
        for i in range(len(tiers) - 1):
            current_tier = tiers[i]
            next_tier = tiers[i + 1]
            self.assertTrue(
                current_tier.level <= next_tier.level or
                (current_tier.level == next_tier.level and 
                 current_tier.earning_type <= next_tier.earning_type)
            )
    
    def test_commission_tiers_display_rates(self):
        """Test that display rates are correctly calculated"""
        response = self.client.get(self.url)
        tiers = response.context['commission_tiers']
        
        for tier in tiers:
            if tier.earning_type == "task_completion":
                expected = f"${tier.rate * Decimal('0.50'):.2f} per $50 task"
                self.assertEqual(tier.display_rate, expected)
            elif tier.earning_type == "advertiser_funding":
                expected = f"${tier.rate:.0f} per $1000 funding"
                self.assertEqual(tier.display_rate, expected)
            elif tier.earning_type == "signup":
                expected = f"${tier.rate * Decimal('0.10'):.2f} per signup"
                self.assertEqual(tier.display_rate, expected)
            else:
                self.assertEqual(tier.display_rate, "Varies by amount")


class AdminReferralDashboardViewTests(BaseTestCase):
    """Test cases for AdminReferralDashboardView"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('referrals:admin_dashboard')
    
    def test_admin_dashboard_requires_login(self):
        """Test that admin dashboard requires authentication"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    def test_admin_dashboard_requires_staff_permission(self):
        """Test that admin dashboard requires staff or superuser permission"""
        # Regular user should be denied
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        
        # Staff user should have access
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Superuser should have access
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
    
    def test_admin_dashboard_context_data(self):
        """Test that admin dashboard provides correct statistics"""
        self.client.force_login(self.staff_user)
        
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        context = response.context
        self.assertEqual(context['total_users'], User.objects.count())
        self.assertEqual(context['total_referrals'], Referral.objects.count())
        self.assertEqual(context['total_earnings'], Decimal('40.00'))  # Sum of all earnings
        self.assertEqual(context['pending_earnings'], Decimal('15.00'))
    
    def test_admin_dashboard_top_referrers(self):
        """Test that admin dashboard shows top referrers correctly"""
        # Create additional referrals for referrer_user
        for i in range(3):
            user = self.create_user(
                username=f'user_{i}',
                email=f'user_{i}@example.com',
                password='testpass123'
            )
            Referral.objects.create(
                referrer=self.referrer_user,
                referred=user,
                level=1,
                referral_code=self.referrer_code
            )
        
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        
        top_referrers = response.context['top_referrers']
        self.assertGreater(len(top_referrers), 0)
        
        # referrer_user should be at the top with most referrals
        top_referrer = top_referrers[0]
        self.assertEqual(top_referrer, self.referrer_user)
        self.assertEqual(top_referrer.referral_count, 4)  # 1 original + 3 new
    
    def test_admin_dashboard_recent_activity(self):
        """Test that admin dashboard shows recent activity"""
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        
        context = response.context
        self.assertEqual(len(context['recent_referrals']), 1)
        self.assertEqual(len(context['recent_earnings']), 2)
        
        # Check ordering (most recent first)
        recent_earnings = context['recent_earnings']
        for i in range(len(recent_earnings) - 1):
            self.assertGreaterEqual(
                recent_earnings[i].created_at,
                recent_earnings[i + 1].created_at
            )


class AdminEarningsManagementViewTests(BaseTestCase):
    """Test cases for AdminEarningsManagementView"""
    
    def setUp(self):
        super().setUp()
        self.url = reverse('referrals:admin_earnings')
    
    def test_admin_earnings_requires_login(self):
        """Test that admin earnings requires authentication"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    def test_admin_earnings_requires_staff_permission(self):
        """Test that admin earnings requires staff or superuser permission"""
        # Regular user should be denied
        self.client.force_login(self.regular_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        
        # Staff user should have access
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        
        # Superuser should have access
        self.client.force_login(self.superuser)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
    
    def test_admin_earnings_shows_all_earnings(self):
        """Test that admin earnings shows all earnings from all users"""
        # Create earning for another user
        other_user = self.create_user(
            username='other',
            email='other@example.com',
            password='testpass123'
        )
        other_referral = Referral.objects.create(
            referrer=other_user,
            referred=self.regular_user,
            level=2,
            referral_code=self.regular_code
        )
        ReferralEarning.objects.create(
            referrer=other_user,
            referred_user=self.regular_user,
            referral=other_referral,
            amount=Decimal('30.00'),
            earning_type='subscription',
            commission_rate=Decimal('15.00'),
            status='pending'
        )
        
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['earnings']), 3)  # All earnings
    
    def test_admin_earnings_status_filter(self):
        """Test that admin earnings can be filtered by status"""
        self.client.force_login(self.staff_user)
        
        # Test filter by pending status
        response = self.client.get(self.url, {'status': 'pending'})
        self.assertEqual(response.status_code, 200)
        earnings = response.context['earnings']
        for earning in earnings:
            self.assertEqual(earning.status, 'pending')
        
        # Test filter by approved status
        response = self.client.get(self.url, {'status': 'approved'})
        earnings = response.context['earnings']
        for earning in earnings:
            self.assertEqual(earning.status, 'approved')
        
        # Test that filter is preserved in context
        self.assertEqual(response.context['status_filter'], 'approved')
    
    def test_admin_earnings_pagination(self):
        """Test admin earnings pagination with large dataset"""
        # Create many earnings
        for i in range(60):
            ReferralEarning.objects.create(
                referrer=self.referrer_user,
                referred_user=self.regular_user,
                referral=self.referral,
                amount=Decimal('1.00'),
                earning_type='task_completion',
                commission_rate=Decimal('10.00'),
                status='approved'
            )
        
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['earnings']), 50)  # paginate_by = 50
        self.assertTrue(response.context['is_paginated'])
    
    def test_admin_earnings_ordering(self):
        """Test that admin earnings are ordered by creation date descending"""
        # Create earning with specific timestamp
        old_earning = ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('99.00'),
            earning_type='advertiser_funding',
            commission_rate=Decimal('2.00'),
            status='approved'
        )
        old_earning.created_at = timezone.now() - timedelta(days=5)
        old_earning.save()
        
        self.client.force_login(self.staff_user)
        response = self.client.get(self.url)
        
        earnings = list(response.context['earnings'])
        # Verify descending order
        for i in range(len(earnings) - 1):
            self.assertGreaterEqual(
                earnings[i].created_at,
                earnings[i + 1].created_at
            )


class ViewMixinsAndHelpersTests(BaseTestCase):
    """Test cases for view mixins and helper functionality"""
    
    def test_login_required_mixin_redirects_anonymous_users(self):
        """Test that LoginRequiredMixin redirects anonymous users properly"""
        urls_requiring_login = [
            reverse('referrals:dashboard'),
            reverse('referrals:referral_list'),
            reverse('referrals:earnings_list'),
            reverse('referrals:admin_dashboard'),
            reverse('referrals:admin_earnings'),
        ]
        
        for url in urls_requiring_login:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('login', response.url)
    
    def test_user_passes_test_mixin_functionality(self):
        """Test UserPassesTestMixin for admin views"""
        admin_urls = [
            reverse('referrals:admin_dashboard'),
            reverse('referrals:admin_earnings'),
        ]
        
        # Test with regular user (should fail)
        self.client.force_login(self.regular_user)
        for url in admin_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
        
        # Test with staff user (should pass)
        self.client.force_login(self.staff_user)
        for url in admin_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
        
        # Test with superuser (should pass)
        self.client.force_login(self.superuser)
        for url in admin_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)


class EdgeCasesAndErrorHandlingTests(BaseTestCase):
    """Test cases for edge cases and error handling scenarios"""
    
    def test_dashboard_with_inactive_referral_code(self):
        """Test dashboard behavior when user has inactive referral code"""
        self.regular_code.is_active = False
        self.regular_code.save()
        
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('referrals:dashboard'))
        
        # Should still work, using the existing code
        self.assertEqual(response.status_code, 200)
        context = response.context
        self.assertEqual(context['referral_code'], self.regular_code)
        self.assertFalse(context['referral_code'].is_active)
    
    def test_dashboard_referral_link_generation_with_custom_domain(self):
        """Test referral link generation works with different domains"""
        self.client.force_login(self.regular_user)
        
        # Test with HTTPS
        response = self.client.get(
            reverse('referrals:dashboard'),
            HTTP_HOST='secure.example.com',
            wsgi={'wsgi.url_scheme': 'https'}
        )
        
        context = response.context
        expected_link = f"http://secure.example.com{reverse('users:register')}?ref={self.regular_code.code}"
        self.assertEqual(context['referral_link'], expected_link)
    
    def test_earnings_aggregation_with_null_values(self):
        """Test earnings aggregation handles null values correctly"""
        # Delete existing earnings to test null case
        ReferralEarning.objects.all().delete()
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(reverse('referrals:dashboard'))
        
        context = response.context
        self.assertEqual(context['total_earnings'], 0)
        self.assertEqual(context['pending_earnings'], 0)
    
    def test_admin_dashboard_with_no_referrals(self):
        """Test admin dashboard when no referrals exist"""
        # Clear all referrals and earnings
        ReferralEarning.objects.all().delete()
        Referral.objects.all().delete()
        
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('referrals:admin_dashboard'))
        
        context = response.context
        self.assertEqual(context['total_referrals'], 0)
        self.assertEqual(context['total_earnings'], 0)
        self.assertEqual(context['pending_earnings'], 0)
        self.assertEqual(len(context['top_referrers']), 0)
        self.assertEqual(len(context['recent_referrals']), 0)
        self.assertEqual(len(context['recent_earnings']), 0)
    
    def test_top_referrers_calculation_accuracy(self):
        """Test that top referrers calculation is accurate"""
        # Create multiple users with different referral counts
        users_data = [
            ('user_5_refs', 5),
            ('user_3_refs', 3),
            ('user_8_refs', 8),
            ('user_1_ref', 1),
        ]
        
        created_users = []
        for username, ref_count in users_data:
            user = self.create_user(
                username=username,
                email=f'{username}@example.com',
                password='testpass123'
            )
            code, _ = ReferralCode.objects.get_or_create(user=user)
            
            # Create referrals for this user
            for i in range(ref_count):
                referred = self.create_user(
                    username=f'{username}_ref_{i}',
                    email=f'{username}_ref_{i}@example.com',
                    password='testpass123'
                )
                Referral.objects.create(
                    referrer=user,
                    referred=referred,
                    level=1,
                    referral_code=code
                )
            
            created_users.append((user, ref_count))
        
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse('referrals:admin_dashboard'))
        
        top_referrers = response.context['top_referrers']
        
        # Check that they're ordered correctly (descending by referral count)
        expected_order = [8, 5, 3, 1, 1]  # Including original referrer_user with 1 referral
        actual_counts = [user.referral_count for user in top_referrers[:5]]
        self.assertEqual(actual_counts, expected_order)
    
    def test_commission_tiers_with_no_active_tiers(self):
        """Test commission tiers view when no active tiers exist"""
        CommissionTier.objects.update(is_active=False)
        
        response = self.client.get(reverse('referrals:commission_tiers'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['commission_tiers']), 0)
    
    def test_earnings_list_with_zero_amounts(self):
        """Test earnings list handles zero amounts correctly"""
        ReferralEarning.objects.create(
            referrer=self.referrer_user,
            referred_user=self.regular_user,
            referral=self.referral,
            amount=Decimal('0.00'),
            earning_type='signup',
            commission_rate=Decimal('0.00'),
            status='approved'
        )
        
        self.client.force_login(self.referrer_user)
        response = self.client.get(reverse('referrals:earnings_list'))
        
        self.assertEqual(response.status_code, 200)
        summary = response.context['earnings_summary']
        # Should include zero amount in total
        self.assertEqual(summary['total'], Decimal('25.00'))  # 25.00 + 0.00
    
    def test_pagination_edge_cases(self):
        """Test pagination edge cases (empty pages, out of range)"""
        self.client.force_login(self.referrer_user)
        
        # Test page that doesn't exist
        response = self.client.get(reverse('referrals:referral_list'), {'page': 999})
        self.assertEqual(response.status_code, 404)
        
        # Test invalid page parameter
        response = self.client.get(reverse('referrals:referral_list'), {'page': 'invalid'})
        self.assertEqual(response.status_code, 404)
        
        # Test page 1 when no data exists
        Referral.objects.filter(referrer=self.referrer_user).delete()
        response = self.client.get(reverse('referrals:referral_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['referrals']), 0)


class DatabaseConstraintTests(BaseTestCase):
    """Test database constraints and model validation"""
    
    def test_referral_code_uniqueness(self):
        """Test that referral codes must be unique"""
        from django.db import IntegrityError
        
        # Try to create another referral code with same code
        with self.assertRaises(IntegrityError):
            ReferralCode.objects.get_or_create(
                user=self.staff_user,
                code=self.regular_code.code
            )
    
    def test_referral_unique_together_constraint(self):
        """Test that referrer-referred pairs must be unique"""
        from django.db import IntegrityError
        
        # Try to create duplicate referral relationship
        with self.assertRaises(IntegrityError):
            Referral.objects.create(
                referrer=self.referrer_user,
                referred=self.regular_user,
                level=2,
                referral_code=self.referrer_code
            )
    
    def test_commission_tier_unique_together_constraint(self):
        """Test that commission tiers level-earning_type pairs must be unique"""
        from django.db import IntegrityError
        
        # Try to create duplicate commission tier
        with self.assertRaises(IntegrityError):
            CommissionTier.objects.create(
                level=1,
                rate=Decimal('15.00'),
                earning_type='task_completion',
                is_active=True
            )


class SecurityTests(BaseTestCase):
    """Test security-related functionality"""
    
    def test_user_cannot_access_other_users_data(self):
        """Test that users can only access their own referral data"""
        # Create another user with their own data
        other_user = self.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )
        
        # User should only see their own referrals
        self.client.force_login(other_user)
        
        response = self.client.get(reverse('referrals:referral_list'))
        self.assertEqual(len(response.context['referrals']), 0)
        
        response = self.client.get(reverse('referrals:earnings_list'))
        self.assertEqual(len(response.context['earnings']), 0)
        
        response = self.client.get(reverse('referrals:dashboard'))
        context = response.context
        self.assertEqual(context['total_referrals'], 0)
        self.assertEqual(context['total_earnings'], 0)
    
    def test_admin_views_require_proper_permissions(self):
        """Test that admin views properly check permissions"""
        # Test with user who is staff but not active
        self.create_user(
            username='inactive_staff',
            email='inactive@example.com',
            password='testpass123',
            is_staff=True,
            is_active=False
        )
        
        # Should not be able to login
        login_successful = self.client.login(
            username='inactive_staff',
            password='testpass123'
        )
        self.assertFalse(login_successful)
    
    def test_referral_code_generation_security(self):
        """Test that referral codes are properly generated and secure"""
        user = self.create_user(
            username='codetest',
            email='codetest@example.com',
            password='testpass123'
        )
        
        # Code should be generated automatically
        code = ReferralCode.objects.get(user=user)
        
        # Code should be 8 characters
        self.assertEqual(len(code.code), 8)
        
        # Code should only contain uppercase letters and digits
        import string
        allowed_chars = string.ascii_uppercase + string.digits
        for char in code.code:
            self.assertIn(char, allowed_chars)
    
    def test_sql_injection_prevention_in_filters(self):
        """Test that filter parameters are properly sanitized"""
        self.client.force_login(self.staff_user)
        
        # Try SQL injection in status filter
        malicious_status = "'; DROP TABLE referrals_referralearning; --"
        response = self.client.get(
            reverse('referrals:admin_earnings'),
            {'status': malicious_status}
        )
        
        # Should not cause an error and should return empty results
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['earnings']), 0)
        self.assertEqual(response.context['status_filter'], malicious_status)


class PerformanceTests(BaseTestCase):
    """Test performance-related functionality"""
    
    def test_dashboard_query_efficiency(self):
        """Test that dashboard doesn't generate excessive database queries"""
        self.client.force_login(self.referrer_user)
        
        with self.assertNumQueries(10):  # Reasonable number of queries
            response = self.client.get(reverse('referrals:dashboard'))
            self.assertEqual(response.status_code, 200)
    
    def test_admin_dashboard_with_large_dataset(self):
        """Test admin dashboard performance with large dataset"""
        # Create a significant amount of test data
        users = []
        for i in range(50):
            user = self.create_user(
                username=f'perfuser_{i}',
                email=f'perfuser_{i}@example.com',
                password='testpass123'
            )
            users.append(user)
        
        # Create referrals and earnings in bulk
        referrals = []
        earnings = []
        
        for i, user in enumerate(users):
            referral = Referral(
                referrer=self.referrer_user,
                referred=user,
                level=1,
                referral_code=self.referrer_code
            )
            referrals.append(referral)
            
        Referral.objects.bulk_create(referrals)
        
        created_referrals = Referral.objects.filter(referrer=self.referrer_user)
        for referral in created_referrals:
            earning = ReferralEarning(
                referrer=referral.referrer,
                referred_user=referral.referred,
                referral=referral,
                amount=Decimal('10.00'),
                earning_type='task_completion',
                commission_rate=Decimal('10.00'),
                status='approved'
            )
            earnings.append(earning)
        
        ReferralEarning.objects.bulk_create(earnings)
        
        self.client.force_login(self.staff_user)
        
        # Should handle large dataset efficiently
        with self.assertNumQueries(12):  # updated to match optimized queries
            response = self.client.get(reverse('referrals:admin_dashboard'))
            self.assertEqual(response.status_code, 200)


class IntegrationTests(BaseTestCase):
    """Integration tests for view interactions"""
    
    def test_referral_dashboard_to_list_view_flow(self):
        """Test user flow from dashboard to detailed list views"""
        self.client.force_login(self.referrer_user)
        
        # Start at dashboard
        dashboard_response = self.client.get(reverse('referrals:dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)
        
        # Navigate to referrals list
        referrals_response = self.client.get(reverse('referrals:referral_list'))
        self.assertEqual(referrals_response.status_code, 200)
        
        # Navigate to earnings list
        earnings_response = self.client.get(reverse('referrals:earnings_list'))
        self.assertEqual(earnings_response.status_code, 200)
        
        # Verify data consistency across views
        dashboard_total = dashboard_response.context['total_referrals']
        list_count = len(referrals_response.context['referrals'])
        self.assertEqual(dashboard_total, list_count)
    
    def test_admin_dashboard_to_earnings_management_flow(self):
        """Test admin flow from dashboard to earnings management"""
        self.client.force_login(self.staff_user)
        
        # Start at admin dashboard
        dashboard_response = self.client.get(reverse('referrals:admin_dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)
        
        # Navigate to earnings management
        earnings_response = self.client.get(reverse('referrals:admin_earnings'))
        self.assertEqual(earnings_response.status_code, 200)
        
        # Apply filter
        filtered_response = self.client.get(
            reverse('referrals:admin_earnings'),
            {'status': 'pending'}
        )
        self.assertEqual(filtered_response.status_code, 200)
        
        # Verify filter worked
        for earning in filtered_response.context['earnings']:
            self.assertEqual(earning.status, 'pending')
    
    def test_commission_tiers_view_accessibility(self):
        """Test that commission tiers are accessible to all user types"""
        url = reverse('referrals:commission_tiers')
        
        # Anonymous user
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Regular user
        self.client.force_login(self.regular_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Staff user
        self.client.force_login(self.staff_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # All should see the same content
        self.client.logout()
        anon_response = self.client.get(url)
        self.client.force_login(self.regular_user)
        user_response = self.client.get(url)
        
        self.assertEqual(
            len(anon_response.context['commission_tiers']),
            len(user_response.context['commission_tiers'])
        )


class ModelInteractionTests(BaseTestCase):
    """Test view interactions with model methods and properties"""
    
    def test_view_handles_model_string_representations(self):
        """Test that views properly handle model __str__ methods"""
        self.client.force_login(self.referrer_user)
        
        # Test that model string representations don't break views
        response = self.client.get(reverse('referrals:referral_list'))
        self.assertEqual(response.status_code, 200)
        
        # Verify referral string representation includes arrow
        referral_str = str(self.referral)
        self.assertIn('→', referral_str)
        self.assertIn(str(self.referrer_user), referral_str)
        self.assertIn(str(self.regular_user), referral_str)
    
    def test_view_handles_model_choices_display(self):
        """Test that views properly handle model choice field displays"""
        self.client.force_login(self.staff_user)
        
        response = self.client.get(reverse('referrals:admin_earnings'))
        self.assertEqual(response.status_code, 200)
        
        # Views should be able to access choice displays
        for earning in response.context['earnings']:
            # These should not raise AttributeError
            status_display = earning.get_status_display()
            earning_type_display = earning.get_earning_type_display()
            self.assertIsNotNone(status_display)
            self.assertIsNotNone(earning_type_display)

