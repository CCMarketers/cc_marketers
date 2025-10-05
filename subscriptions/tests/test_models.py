# tests/test_models.py
from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
import time

from subscriptions.models import SubscriptionPlan, UserSubscription
from .test_base import BaseTestMixin


class SubscriptionPlanModelTest(BaseTestMixin, TestCase):
    """Test SubscriptionPlan model"""

    def test_subscription_plan_creation(self):
        """Test creating a subscription plan"""
        plan = SubscriptionPlan.objects.create(
            name='Test Plan',
            price=Decimal('15.00'),
            duration_days=30,
            business_volume=1000,
            referral_commission=Decimal('2.50'),
            commission_to_tree=Decimal('1.25'),
            daily_ad_limit=25
        )
        
        self.assertEqual(plan.name, 'Test Plan')
        self.assertDecimalEqual(plan.price, Decimal('15.00'))
        self.assertEqual(plan.duration_days, 30)
        self.assertEqual(plan.business_volume, 1000)
        self.assertDecimalEqual(plan.referral_commission, Decimal('2.50'))
        self.assertDecimalEqual(plan.commission_to_tree, Decimal('1.25'))
        self.assertEqual(plan.daily_ad_limit, 25)
        self.assertTrue(plan.is_active)
        self.assertIsNotNone(plan.created_at)

    def test_subscription_plan_str_representation(self):
        """Test string representation of subscription plan"""
        plan = self.create_subscription_plan(name='Premium Plan', price=Decimal('20.00'))
        self.assertEqual(str(plan), 'Premium Plan - $20.00')

    def test_subscription_plan_ordering(self):
        """Test subscription plans are ordered by price"""
        plan1 = self.create_subscription_plan(name='Expensive', price=Decimal('50.00'))
         
        time.sleep(1)
        plan2 = self.create_subscription_plan(name='Cheap', price=Decimal('1.00'))
    
        time.sleep(1)  # unique lowest
        self.create_subscription_plan(name='Medium', price=Decimal('15.00'))

        
        plans = list(SubscriptionPlan.objects.all())
        self.assertEqual(plans[0], plan2)  # Cheapest first
        self.assertEqual(plans[-1], plan1)  # Most expensive last

    def test_subscription_plan_defaults(self):
        """Test subscription plan default values"""
        plan = SubscriptionPlan.objects.create(
            name='Minimal Plan',
            price=Decimal('5.00')
        )
        
        self.assertEqual(plan.duration_days, 30)
        self.assertEqual(plan.business_volume, 0)
        self.assertDecimalEqual(plan.referral_commission, Decimal('0.00'))
        self.assertDecimalEqual(plan.commission_to_tree, Decimal('0.00'))
        self.assertEqual(plan.daily_ad_limit, 0)
        self.assertTrue(plan.is_active)

    def test_subscription_plan_inactive(self):
        """Test inactive subscription plan"""
        plan = self.create_subscription_plan(is_active=False)
        self.assertFalse(plan.is_active)


class UserSubscriptionModelTest(BaseTestMixin, TestCase):
    """Test UserSubscription model"""

    def test_user_subscription_creation(self):
        """Test creating a user subscription"""
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=self.basic_plan,
            expiry_date=timezone.now() + timedelta(days=30)
        )
        
        self.assertEqual(subscription.user, self.user)
        self.assertEqual(subscription.plan, self.basic_plan)
        self.assertEqual(subscription.status, 'active')
        self.assertTrue(subscription.auto_renewal)
        self.assertIsNotNone(subscription.start_date)
        self.assertIsNotNone(subscription.created_at)

    def test_user_subscription_auto_expiry_date(self):
        """Test subscription automatically sets expiry date"""
        start_time = timezone.now()
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=self.basic_plan
        )
        
        # Should set expiry_date based on plan duration
        expected_expiry = start_time + timedelta(days=self.basic_plan.duration_days)
        time_diff = abs((subscription.expiry_date - expected_expiry).total_seconds())
        self.assertLess(time_diff, 60)  # Within 1 minute

    def test_user_subscription_str_representation(self):
        """Test string representation of user subscription"""
        subscription = self.create_subscription()
        expected = f"{self.user.get_display_name()} - {self.basic_plan.name} (active)"
        self.assertEqual(str(subscription), expected)

    def test_user_subscription_is_active_property(self):
        """Test is_active property"""
        # Active subscription
        future_date = timezone.now() + timedelta(days=10)
        active_subscription = self.create_subscription(
            expiry_date=future_date,
            status='active'
        )
        self.assertTrue(active_subscription.is_active)
        
        # Expired subscription
        past_date = timezone.now() - timedelta(days=1)
        expired_subscription = self.create_subscription(
            user=self.user2,
            expiry_date=past_date,
            status='active'
        )
        self.assertFalse(expired_subscription.is_active)
        
        # Cancelled subscription
        cancelled_subscription = self.create_subscription(
            user=self.user2,
            plan=self.premium_plan,
            status='cancelled'
        )
        self.assertFalse(cancelled_subscription.is_active)

    def test_user_subscription_days_remaining(self):
        """Test days_remaining property"""
        # Future subscription
        future_date = timezone.now() + timedelta(days=15, hours=12)
        subscription = self.create_subscription(expiry_date=future_date)
        self.assertEqual(subscription.days_remaining, 15)
        
        # Expired subscription
        past_date = timezone.now() - timedelta(days=5)
        expired_subscription = self.create_subscription(
            user=self.user2,
            expiry_date=past_date
        )
        self.assertEqual(expired_subscription.days_remaining, 0)

    def test_user_subscription_ordering(self):
        """Test user subscriptions are ordered by created_at descending"""
        self.create_subscription()
        time.sleep(1)  # force different timestamps
        sub2 = self.create_subscription(user=self.user2, plan=self.premium_plan)

        
        subscriptions = list(UserSubscription.objects.all())
        self.assertEqual(subscriptions[0], sub2)  # Most recent first

    def test_user_subscription_status_choices(self):
        """Test subscription status choices"""
        # Active status
        active_sub = self.create_subscription(status='active')
        self.assertEqual(active_sub.status, 'active')
        
        # Expired status
        expired_sub = self.create_subscription(
            user=self.user2,
            status='expired'
        )
        self.assertEqual(expired_sub.status, 'expired')
        
        # Cancelled status
        cancelled_sub = UserSubscription.objects.create(
            user=self.admin_user,
            plan=self.business_plan,
            status='cancelled',
            expiry_date=timezone.now() + timedelta(days=30)
        )
        self.assertEqual(cancelled_sub.status, 'cancelled')

    def test_user_subscription_auto_renewal_toggle(self):
        """Test auto renewal can be toggled"""
        subscription = self.create_subscription(auto_renewal=True)
        self.assertTrue(subscription.auto_renewal)
        
        subscription.auto_renewal = False
        subscription.save()
        subscription.refresh_from_db()
        self.assertFalse(subscription.auto_renewal)

    def test_user_subscription_related_name(self):
        """Test related name for user subscriptions"""
        self.create_subscription()
        self.create_subscription(plan=self.premium_plan)
        
        user_subscriptions = self.user.subscriptions.all()
        self.assertEqual(user_subscriptions.count(), 2)

    def test_user_subscription_cascade_delete(self):
        """Test subscription is deleted when user is deleted"""
        subscription = self.create_subscription()
        subscription_id = subscription.id
        
        self.user.delete()
        
        with self.assertRaises(UserSubscription.DoesNotExist):
            UserSubscription.objects.get(id=subscription_id)

    def test_user_subscription_plan_cascade_protection(self):
        """Test subscription plan deletion behavior"""
        self.create_subscription()
        plan_id = self.basic_plan.id
        
        # This should work since cascade is default
        self.basic_plan.delete()
        
        with self.assertRaises(UserSubscription.DoesNotExist):
            UserSubscription.objects.get(plan_id=plan_id)

    def test_multiple_subscriptions_same_user(self):
        """Test user can have multiple subscriptions (history)"""
        # Create first subscription
        sub1 = self.create_subscription(
            plan=self.basic_plan,
            status='expired'
        )
        
        # Create second subscription
        sub2 = self.create_subscription(
            plan=self.premium_plan,
            status='active'
        )
        
        user_subscriptions = self.user.subscriptions.all()
        self.assertEqual(user_subscriptions.count(), 2)
        self.assertIn(sub1, user_subscriptions)
        self.assertIn(sub2, user_subscriptions)

    def test_subscription_edge_cases(self):
        """Test edge cases for subscription model"""
        # Subscription expiring exactly now
        now = timezone.now()
        subscription = self.create_subscription(expiry_date=now)
        
        # Should not be active if expires exactly now
        self.assertFalse(subscription.is_active)
        
        # Days remaining should be 0
        self.assertEqual(subscription.days_remaining, 0)