# payments/tests/test_admin.py
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model

from payments.admin import (
    PaymentGatewayAdmin, PaymentTransactionAdmin, 
    PaystackTransactionAdmin, WebhookEventAdmin
)
from payments.models import (
    PaymentGateway, PaymentTransaction, PaystackTransaction, WebhookEvent
)
from .test_base import BaseTestCase

User = get_user_model()


class MockRequest:
    """Mock request for admin tests"""
    pass


class PaymentGatewayAdminTestCase(BaseTestCase):
    """Test cases for PaymentGatewayAdmin"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = PaymentGatewayAdmin(PaymentGateway, self.site)
        self.request = MockRequest()
    
    def test_list_display(self):
        """Test admin list display fields"""
        expected_fields = ['name', 'is_active', 'created_at']
        self.assertEqual(list(self.admin.list_display), expected_fields)
    
    def test_list_filter(self):
        """Test admin list filter fields"""
        expected_filters = ['is_active', 'created_at']
        self.assertEqual(list(self.admin.list_filter), expected_filters)
    
    def test_search_fields(self):
        """Test admin search fields"""
        expected_fields = ['name']
        self.assertEqual(list(self.admin.search_fields), expected_fields)
    
    def test_readonly_fields(self):
        """Test admin readonly fields"""
        expected_fields = ['created_at']
        self.assertEqual(list(self.admin.readonly_fields), expected_fields)


class PaymentTransactionAdminTestCase(BaseTestCase):
    """Test cases for PaymentTransactionAdmin"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = PaymentTransactionAdmin(PaymentTransaction, self.site)
        self.request = MockRequest()
        self.transaction = self.create_payment_transaction()
    
    def test_list_display(self):
        """Test admin list display fields"""
        expected_fields = [
            'internal_reference', 'user', 'transaction_type', 'amount',
            'currency', 'status', 'gateway', 'created_at'
        ]
        self.assertEqual(list(self.admin.list_display), expected_fields)
    
    def test_list_filter(self):
        """Test admin list filter fields"""
        expected_filters = [
            'transaction_type', 'status', 'gateway', 'currency', 'created_at'
        ]
        self.assertEqual(list(self.admin.list_filter), expected_filters)
    
    def test_search_fields(self):
        """Test admin search fields"""
        expected_fields = [
            'user__username', 'user__email', 'gateway_reference', 'internal_reference'
        ]
        self.assertEqual(list(self.admin.search_fields), expected_fields)
    
    def test_readonly_fields(self):
        """Test admin readonly fields"""
        expected_fields = ['id', 'internal_reference', 'created_at', 'updated_at', 'completed_at']
        self.assertEqual(list(self.admin.readonly_fields), expected_fields)
    
    def test_date_hierarchy(self):
        """Test admin date hierarchy"""
        self.assertEqual(self.admin.date_hierarchy, 'created_at')
    
    def test_get_queryset_optimization(self):
        """Test that admin queryset uses select_related for optimization"""
        queryset = self.admin.get_queryset(self.request)
        
        # Check that select_related is used
        self.assertIn('user', queryset.query.select_related)
        self.assertIn('gateway', queryset.query.select_related)
    
    def test_colored_status_method(self):
        """Test colored_status admin method"""
        # Test different status colors
        test_cases = [
            ('pending', '#fbbf24'),
            ('success', '#10b981'),
            ('failed', '#ef4444'),
            ('cancelled', '#6b7280')
        ]
        
        for status, expected_color in test_cases:
            with self.subTest(status=status):
                self.transaction.status = status
                result = self.admin.colored_status(self.transaction)
                
                self.assertIn(expected_color, result)
                self.assertIn(status, result.lower())


class PaystackTransactionAdminTestCase(BaseTestCase):
    """Test cases for PaystackTransactionAdmin"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = PaystackTransactionAdmin(PaystackTransaction, self.site)
        self.request = MockRequest()
        
        self.transaction = self.create_payment_transaction()
        self.paystack_transaction = self.create_paystack_transaction(self.transaction)
    
    def test_list_display(self):
        """Test admin list display fields"""
        expected_fields = ['transaction', 'paystack_reference', 'recipient_code', 'created_at']
        self.assertEqual(list(self.admin.list_display), expected_fields)
    
    def test_list_filter(self):
        """Test admin list filter fields"""
        expected_filters = ['created_at']
        self.assertEqual(list(self.admin.list_filter), expected_filters)
    
    def test_search_fields(self):
        """Test admin search fields"""
        expected_fields = [
            'paystack_reference', 'transaction__gateway_reference',
            'transaction__user__username'
        ]
        self.assertEqual(list(self.admin.search_fields), expected_fields)
    
    def test_readonly_fields(self):
        """Test admin readonly fields"""
        expected_fields = ['created_at']
        self.assertEqual(list(self.admin.readonly_fields), expected_fields)
    
    def test_get_queryset_optimization(self):
        """Test that admin queryset uses select_related for optimization"""
        queryset = self.admin.get_queryset(self.request)
        
        # Check that select_related is used
        self.assertIn('transaction__user', queryset.query.select_related)


class WebhookEventAdminTestCase(BaseTestCase):
    """Test cases for WebhookEventAdmin"""
    
    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.admin = WebhookEventAdmin(WebhookEvent, self.site)
        self.request = MockRequest()
        self.webhook_event = self.create_webhook_event('TEST_WEBHOOK_REF')
    
    def test_list_display(self):
        """Test admin list display fields"""
        expected_fields = ['reference', 'gateway', 'event_type', 'processed', 'created_at']
        self.assertEqual(list(self.admin.list_display), expected_fields)
    
    def test_list_filter(self):
        """Test admin list filter fields"""
        expected_filters = ['gateway', 'event_type', 'processed', 'created_at']
        self.assertEqual(list(self.admin.list_filter), expected_filters)
    
    def test_search_fields(self):
        """Test admin search fields"""
        expected_fields = ['reference']
        self.assertEqual(list(self.admin.search_fields), expected_fields)
    
    def test_readonly_fields(self):
        """Test admin readonly fields"""
        expected_fields = ['id', 'created_at', 'processed_at']
        self.assertEqual(list(self.admin.readonly_fields), expected_fields)
    
    def test_date_hierarchy(self):
        """Test admin date hierarchy"""
        self.assertEqual(self.admin.date_hierarchy, 'created_at')
    
    def test_get_queryset_optimization(self):
        """Test that admin queryset uses select_related for optimization"""
        queryset = self.admin.get_queryset(self.request)
        
        # Check that select_related is used
        self.assertIn('gateway', queryset.query.select_related)


class AdminRegistrationTestCase(BaseTestCase):
    """Test that all models are properly registered with admin"""
    
    def test_models_registered_with_admin(self):
        """Test that all payment models are registered with Django admin"""
        from django.contrib import admin
        
        # Check that models are registered
        self.assertIn(PaymentGateway, admin.site._registry)
        self.assertIn(PaymentTransaction, admin.site._registry)
        self.assertIn(PaystackTransaction, admin.site._registry)
        self.assertIn(WebhookEvent, admin.site._registry)
    
    def test_admin_classes_used(self):
        """Test that correct admin classes are used for models"""
        from django.contrib import admin
        
        self.assertIsInstance(admin.site._registry[PaymentGateway], PaymentGatewayAdmin)
        self.assertIsInstance(admin.site._registry[PaymentTransaction], PaymentTransactionAdmin)
        self.assertIsInstance(admin.site._registry[PaystackTransaction], PaystackTransactionAdmin)
        self.assertIsInstance(admin.site._registry[WebhookEvent], WebhookEventAdmin)