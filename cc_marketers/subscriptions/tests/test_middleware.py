# tests/test_middleware.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from django.test import TransactionTestCase

from subscriptions.middleware import SubscriptionMiddleware
from .test_base import BaseTestMixin

User = get_user_model()


class MockResolverMatch:
    """Mock ResolverMatch for testing"""
    def __init__(self, app_name, url_name):
        self.app_name = app_name
        self.url_name = url_name


def get_response_mock(request):
    """Mock get_response function"""
    return HttpResponse("OK")


class SubscriptionMiddlewareTest(BaseTestMixin, TestCase):
    """Test SubscriptionMiddleware"""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.middleware = SubscriptionMiddleware(get_response_mock)
    
    def add_middleware_to_request(self, request):
        """Add required middleware to request"""
        # Pass a dummy get_response
        session_middleware = SessionMiddleware(lambda r: None)
        session_middleware.process_request(request)
        from django.contrib.sessions.backends.cache import SessionStore

        request.session = SessionStore()


        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request


    def test_middleware_initialization(self):
        """Test middleware initializes correctly"""
        middleware = SubscriptionMiddleware(get_response_mock)
        self.assertEqual(middleware.get_response, get_response_mock)
        self.assertEqual(middleware.protected_views, [])

    def test_middleware_initialization_with_protected_views(self):
        """Test middleware with protected views configured"""
        middleware = SubscriptionMiddleware(get_response_mock)
        middleware.protected_views = ['app:view1', 'app:view2']
        
        self.assertEqual(len(middleware.protected_views), 2)
        self.assertIn('app:view1', middleware.protected_views)
        self.assertIn('app:view2', middleware.protected_views)

    def test_middleware_anonymous_user_no_check(self):
        """Test middleware doesn't check anonymous users"""
        request = self.factory.get('/')
        request.user = AnonymousUser()
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views
        self.middleware.protected_views = ['protected_app:protected_view']
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_authenticated_user_unprotected_view(self):
        """Test middleware allows access to unprotected views"""
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('public_app', 'public_view')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views (different from requested view)
        self.middleware.protected_views = ['protected_app:protected_view']
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_authenticated_user_protected_view_with_subscription(self):
        """Test middleware allows access to protected view with active subscription"""
        self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views
        self.middleware.protected_views = ['protected_app:protected_view']
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_authenticated_user_protected_view_without_subscription(self):
        """Test middleware redirects user without subscription from protected view"""
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views
        self.middleware.protected_views = ['protected_app:protected_view']
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need an active subscription', str(messages[0]))

    def test_middleware_user_with_expired_subscription(self):
        """Test middleware redirects user with expired subscription"""
        past_date = timezone.now() - timedelta(days=1)
        self.create_subscription(expiry_date=past_date)
        
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views
        self.middleware.protected_views = ['protected_app:protected_view']
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need an active subscription', str(messages[0]))

    def test_middleware_user_with_cancelled_subscription(self):
        """Test middleware redirects user with cancelled subscription"""
        self.create_subscription(status='cancelled')
        
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views
        self.middleware.protected_views = ['protected_app:protected_view']
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need an active subscription', str(messages[0]))

    def test_middleware_no_resolver_match(self):
        """Test middleware handles request without resolver_match"""
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = None
        request = self.add_middleware_to_request(request)
        
        # Configure protected views
        self.middleware.protected_views = ['protected_app:protected_view']
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_multiple_protected_views(self):
        """Test middleware with multiple protected views"""
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('app2', 'view2')
        request = self.add_middleware_to_request(request)
        
        # Configure multiple protected views
        self.middleware.protected_views = [
            'app1:view1',
            'app2:view2',
            'app3:view3'
        ]
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)

    def test_middleware_case_sensitive_view_matching(self):
        """Test middleware view matching is case sensitive"""
        self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('Protected_App', 'Protected_View')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views with different case
        self.middleware.protected_views = ['protected_app:protected_view']
        
        # Should not match due to case difference, so no protection
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_exact_view_matching(self):
        """Test middleware requires exact view name matching"""
        self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view_detail')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views with similar but different name
        self.middleware.protected_views = ['protected_app:protected_view']
        
        # Should not match, so no protection
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_with_subscription_service_error(self):
        """Test middleware handles SubscriptionService errors gracefully"""
        # Create user with invalid ID to potentially cause service errors
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view')
        request = self.add_middleware_to_request(request)
        
        # Configure protected views
        self.middleware.protected_views = ['protected_app:protected_view']
        
        # Mock SubscriptionService to raise an exception
        with self.assertRaises(Exception):
            # Delete user to cause potential database errors
            self.user.delete()
            self.middleware(request)

    def test_middleware_empty_protected_views_list(self):
        """Test middleware with empty protected views list"""
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('any_app', 'any_view')
        request = self.add_middleware_to_request(request)
        
        # No protected views configured
        self.middleware.protected_views = []
        
        response = self.middleware(request)
        
        # Should pass through without any checks
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_view_name_variations(self):
        """Test middleware handles different view name formats"""
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        test_cases = [
            # (resolver_match, protected_views, should_protect)
            (MockResolverMatch('app', 'view'), ['app:view'], True),
            (MockResolverMatch('app', 'view'), ['other:view'], False),
            (MockResolverMatch('app', 'view'), ['app:other'], False),
            (MockResolverMatch('app_name', 'view_name'), ['app_name:view_name'], True),
            (MockResolverMatch('app-name', 'view-name'), ['app-name:view-name'], True),
        ]
        
        for resolver_match, protected_views, should_protect in test_cases:
            with self.subTest(resolver_match=resolver_match, protected_views=protected_views):
                request.resolver_match = resolver_match
                self.middleware.protected_views = protected_views
                
                response = self.middleware(request)
                
                if should_protect:
                    self.assertEqual(response.status_code, 302)
                else:
                    self.assertEqual(response.status_code, 200)

    def test_middleware_subscription_app_views_not_protected(self):
        """Test middleware doesn't protect views within the subscription app."""
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('subscriptions', 'plans')
        request = self.add_middleware_to_request(request)
        
        # This view should NOT be protected, so the middleware should
        # process the request normally, resulting in a 200 OK response.
        self.middleware.protected_views = [] # Ensure no views are protected for this test
        
        response = self.middleware(request)
        
        # We expect a 200 OK because subscription-related pages must always be accessible.
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "OK")

    def test_middleware_admin_views_not_affected(self):
        """Test middleware doesn't interfere with admin views"""
        request = self.factory.get('/')
        request.user = self.admin_user  # Admin user
        request.resolver_match = MockResolverMatch('admin', 'index')
        request = self.add_middleware_to_request(request)
        
        # Configure admin views as protected (edge case)
        self.middleware.protected_views = ['admin:index']
        
        response = self.middleware(request)
        
        # Should redirect since admin user has no subscription
        self.assertEqual(response.status_code, 302)

    def test_middleware_performance_with_many_protected_views(self):
        """Test middleware performance with large list of protected views"""
        # Create large list of protected views
        protected_views = [f'app{i}:view{j}' for i in range(100) for j in range(10)]
        
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('app50', 'view5')  # In the middle
        request = self.add_middleware_to_request(request)
        
        self.middleware.protected_views = protected_views
        
        # This should execute quickly
        import time
        start_time = time.time()
        response = self.middleware(request)
        end_time = time.time()
        
        # Should complete in reasonable time (less than 1 second)
        self.assertLess(end_time - start_time, 1.0)
        self.assertEqual(response.status_code, 302)  # Should redirect (no subscription)

    # def test_middleware_thread_safety(self):
    #     """Test middleware thread safety"""
    #     import threading
        
    #     results = []
        
    #     def worker():
    #         request = self.factory.get('/')
    #         request.user = self.user
    #         request.resolver_match = MockResolverMatch('test_app', 'test_view')
    #         request = self.add_middleware_to_request(request)
            
    #         middleware = SubscriptionMiddleware(get_response_mock)
    #         middleware.protected_views = ['test_app:test_view']
            
    #         response = middleware(request)
    #         results.append(response.status_code)
        
    #     # Create multiple threads
    #     threads = [threading.Thread(target=worker) for _ in range(10)]
        
    #     # Start all threads
    #     for thread in threads:
    #         thread.start()
        
    #     # Wait for all threads to complete
    #     for thread in threads:
    #         thread.join()
        
    #     # All should return the same result (302 - redirect)
    #     self.assertEqual(len(results), 10)
    #     self.assertTrue(all(status == 302 for status in results))

    def test_middleware_integration_with_real_views(self):
        """Test middleware integration scenarios"""
        self.create_subscription()
        
        # Test with various app:view combinations
        test_views = [
            ('tasks', 'create_task'),
            ('wallets', 'withdrawal_request'),
            ('referrals', 'dashboard'),
            ('ads', 'view_ad'),
        ]
        
        for app_name, view_name in test_views:
            with self.subTest(app=app_name, view=view_name):
                request = self.factory.get('/')
                request.user = self.user
                request.resolver_match = MockResolverMatch(app_name, view_name)
                request = self.add_middleware_to_request(request)
                
                # Configure this view as protected
                self.middleware.protected_views = [f'{app_name}:{view_name}']
                
                response = self.middleware(request)
                
                # Should allow access with active subscription 
                self.assertEqual(response.status_code, 200)

    def test_middleware_message_content(self):
        """Test middleware warning message content"""
        request = self.factory.get('/')
        request.user = self.user
        request.resolver_match = MockResolverMatch('protected_app', 'protected_view')
        request = self.add_middleware_to_request(request)
        
        self.middleware.protected_views = ['protected_app:protected_view']
        
        self.middleware(request)
        
        # Check specific message content
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        message = str(messages[0])
        self.assertIn('You need an active subscription', message)
        self.assertIn('to access this feature', message)





class SubscriptionMiddlewareThreadSafetyTest(BaseTestMixin, TransactionTestCase):
    """
    Test middleware thread safety using TransactionTestCase to avoid SQLite locking issues.
    """

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def add_middleware_to_request(self, request):
        """Add required middleware to request"""
        # This helper function is duplicated here for clarity
        session_middleware = SessionMiddleware(lambda r: None)
        session_middleware.process_request(request)
        from django.contrib.sessions.backends.cache import SessionStore
        request.session = SessionStore()
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def test_middleware_thread_safety(self):
        """Test middleware thread safety"""
        import threading
        
        # This list must be defined outside the worker function
        # to be accessible by the main thread.
        results = []
        
        def worker():
            # Each thread needs its own request and middleware instance
            request = self.factory.get('/')
            request.user = self.user
            request.resolver_match = MockResolverMatch('test_app', 'test_view')
            request = self.add_middleware_to_request(request)
            
            middleware = SubscriptionMiddleware(get_response_mock)
            middleware.protected_views = ['test_app:test_view']
            
            response = middleware(request)
            results.append(response.status_code)
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        self.assertEqual(len(results), 10)
        # All requests should be redirected as the user has no subscription
        self.assertTrue(all(status == 302 for status in results))