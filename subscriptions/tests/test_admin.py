# tests/test_admin.py
from django.test import TestCase, Client
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.urls import reverse
from decimal import Decimal

from subscriptions.admin import SubscriptionPlanAdmin, UserSubscriptionAdmin
from subscriptions.models import SubscriptionPlan, UserSubscription
from .test_base import BaseTestMixin

User = get_user_model()


class MockRequest:
    """Mock request object for admin tests"""
    pass


class SubscriptionPlanAdminTest(BaseTestMixin, TestCase):
    """Test SubscriptionPlan admin interface"""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = SubscriptionPlanAdmin(SubscriptionPlan, self.site)

    def test_list_display(self):
        """Test admin list display fields"""
        expected_fields = ['name', 'price', 'duration_days', 'daily_ad_limit', 'is_active']
        self.assertEqual(list(self.admin.list_display), expected_fields)

    def test_list_filter(self):
        """Test admin list filter fields"""
        expected_filters = ['is_active', 'duration_days']
        self.assertEqual(list(self.admin.list_filter), expected_filters)

    def test_search_fields(self):
        """Test admin search fields"""
        expected_fields = ['name']
        self.assertEqual(list(self.admin.search_fields), expected_fields)

    def test_ordering(self):
        """Test admin ordering"""
        expected_ordering = ['price']
        self.assertEqual(list(self.admin.ordering), expected_ordering)

    def test_admin_queryset_ordering(self):
        """Test that admin queryset respects ordering"""
        # Create plans with different prices
        self.create_subscription_plan(
            name='Expensive',
            price=Decimal('100.00')
        )
        self.create_subscription_plan(
            name='Cheap',
            price=Decimal('5.00')
        )
        
        queryset = self.admin.get_queryset(MockRequest())
        plans = list(queryset)
        
        # Should be ordered by price
        self.assertLess(plans[0].price, plans[-1].price)


class UserSubscriptionAdminTest(BaseTestMixin, TestCase):
    """Test UserSubscription admin interface"""

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = UserSubscriptionAdmin(UserSubscription, self.site)

    def test_list_display(self):
        """Test admin list display fields"""
        expected_fields = [
            'user', 'plan', 'status', 'start_date', 'expiry_date', 'auto_renewal'
        ]
        self.assertEqual(list(self.admin.list_display), expected_fields)

    def test_list_filter(self):
        """Test admin list filter fields"""
        expected_filters = ['status', 'auto_renewal', 'plan']
        self.assertEqual(list(self.admin.list_filter), expected_filters)

    def test_search_fields(self):
        """Test admin search fields"""
        expected_fields = ['user__username', 'plan__name']
        self.assertEqual(list(self.admin.search_fields), expected_fields)

    def test_ordering(self):
        """Test admin ordering"""
        expected_ordering = ['-created_at']
        self.assertEqual(list(self.admin.ordering), expected_ordering)

    def test_readonly_fields(self):
        """Test admin readonly fields"""
        expected_fields = ['start_date', 'created_at']
        self.assertEqual(list(self.admin.readonly_fields), expected_fields)

    def test_admin_queryset_ordering(self):
        """Test that admin queryset respects ordering"""
        # Create subscriptions at different times
        self.create_subscription(user=self.user)
        self.create_subscription(user=self.user2, plan=self.premium_plan)
        
        queryset = self.admin.get_queryset(MockRequest())
        subscriptions = list(queryset)
        
        # Should be ordered by created_at descending (newest first)
        self.assertGreaterEqual(
            subscriptions[0].created_at,
            subscriptions[-1].created_at
        )


class AdminIntegrationTest(BaseTestMixin, TestCase):
    """Test admin interface integration"""

    def setUp(self):
        super().setUp()
        self.client = Client()
        # Create admin user and login
        self.admin_user = User.objects.create_superuser(
            
            email='admin@test.com',
            password='adminpass123'
        )
        self.client.login(email='admin@test.com', password='adminpass123')

    def test_subscription_plan_admin_changelist(self):
        """Test subscription plan admin changelist view"""
        url = reverse('admin:subscriptions_subscriptionplan_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_plan.name)
        self.assertContains(response, self.business_plan.name)
        self.assertContains(response, self.premium_plan.name)

    def test_subscription_plan_admin_add(self):
        """Test adding subscription plan through admin"""
        url = reverse('admin:subscriptions_subscriptionplan_add')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add subscription plan')

    def test_subscription_plan_admin_change(self):
        """Test changing subscription plan through admin"""
        url = reverse('admin:subscriptions_subscriptionplan_change', args=[self.basic_plan.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.basic_plan.name)

    def test_subscription_plan_admin_delete(self):
        """Test deleting subscription plan through admin"""
        plan = self.create_subscription_plan(name='Test Delete Plan')
        url = reverse('admin:subscriptions_subscriptionplan_delete', args=[plan.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure')

    def test_user_subscription_admin_changelist(self):
        """Test user subscription admin changelist view"""
        subscription = self.create_subscription()
        
        url = reverse('admin:subscriptions_usersubscription_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(subscription.user))  # uses __str__ of User
        self.assertContains(response, subscription.plan.name)

    def test_user_subscription_admin_add(self):
        """Test adding user subscription through admin"""
        url = reverse('admin:subscriptions_usersubscription_add')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add user subscription')

    def test_user_subscription_admin_change(self):
        """Test changing user subscription through admin"""
        subscription = self.create_subscription()
        url = reverse('admin:subscriptions_usersubscription_change', args=[subscription.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, subscription.plan.name)

    def test_user_subscription_admin_readonly_fields(self):
        """Test readonly fields are not editable in admin"""
        subscription = self.create_subscription()
        url = reverse('admin:subscriptions_usersubscription_change', args=[subscription.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check that readonly fields are present but not in input forms
        self.assertContains(response, 'Start date:')
        self.assertContains(response, 'Created at:')

    def test_admin_search_functionality(self):
        """Test admin search functionality"""
        subscription = self.create_subscription()
        
        # Test search by username
        url = reverse('admin:subscriptions_usersubscription_changelist')
        response = self.client.get(url, {'q': self.user.username})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(subscription.user))  # uses __str__ of User

    def test_admin_filter_functionality(self):
        """Test admin filter functionality"""
        active_sub = self.create_subscription(status='active')
        self.create_subscription(
            user=self.user2,
            status='expired'
        )
         
        # Test filter by status
        url = reverse('admin:subscriptions_usersubscription_changelist')
        response = self.client.get(url, {'status__exact': 'active'})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, active_sub.user.get_full_name())

    def test_admin_plan_filter(self):
        """Test filtering by subscription plan in admin"""
        basic_sub = self.create_subscription(plan=self.basic_plan)
        self.create_subscription(
            user=self.user2,
            plan=self.premium_plan
        )
        
        # Test filter by plan
        url = reverse('admin:subscriptions_usersubscription_changelist')
        response = self.client.get(url, {'plan__id__exact': self.basic_plan.id})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, basic_sub.user.get_full_name())

    def test_admin_permissions(self):
        """Test admin permissions for different user types"""
        # Test with regular user (should be denied)
        regular_client = Client()
        regular_client.login(username=self.user.username, password='testpass123')
        
        url = reverse('admin:subscriptions_subscriptionplan_changelist')
        response = regular_client.get(url)
        
        # Should redirect to admin login
        self.assertEqual(response.status_code, 302)

    def test_subscription_plan_admin_bulk_actions(self):
        """Test bulk actions in subscription plan admin"""
        plan1 = self.create_subscription_plan(name='Plan 1')
        plan2 = self.create_subscription_plan(name='Plan 2')
        
        url = reverse('admin:subscriptions_subscriptionplan_changelist')
        response = self.client.post(url, {
            'action': 'delete_selected',
            '_selected_action': [plan1.id, plan2.id],
            'post': 'yes'
        })
        
        # Should redirect back to changelist
        self.assertEqual(response.status_code, 302)

    def test_admin_display_values(self):
        """Test admin displays correct values"""
        subscription = self.create_subscription()
        
        url = reverse('admin:subscriptions_usersubscription_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        # Check that all display fields show correct values
        self.assertContains(response, str(subscription.user))  # uses __str__ of User
        self.assertContains(response, subscription.plan.name)
        self.assertContains(response, subscription.get_status_display())
        self.assertContains(response, 'Yes' if subscription.auto_renewal else 'No')

    def test_subscription_plan_ordering_in_admin(self):
        """Test subscription plans are ordered by price in admin"""
        expensive = self.create_subscription_plan(
            name='Expensive Plan',
            price=Decimal('50.00')
        )
        cheap = self.create_subscription_plan(
            name='Cheap Plan',
            price=Decimal('1.00')
        )
        
        url = reverse('admin:subscriptions_subscriptionplan_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Cheap plan should appear before expensive plan in the HTML
        cheap_pos = content.find(cheap.name)
        expensive_pos = content.find(expensive.name)
        self.assertLess(cheap_pos, expensive_pos)

    def test_user_subscription_ordering_in_admin(self):
        """Test user subscriptions are ordered by created_at desc in admin"""
        old_sub = self.create_subscription()
        # Create newer subscription
        new_sub = self.create_subscription(
            user=self.user2,
            plan=self.premium_plan
        )
        
        url = reverse('admin:subscriptions_usersubscription_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        response.content.decode()
        

        qs = response.context['cl'].queryset
        self.assertEqual(qs[0], new_sub)
        self.assertEqual(qs[1], old_sub)
