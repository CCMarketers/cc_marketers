# tests/test_decorators.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from subscriptions.decorators import subscription_required, plan_required
from .test_base import BaseTestMixin

User = get_user_model()


def dummy_view(request):
    """Dummy view for testing decorators"""
    return HttpResponse("Success")


class SubscriptionRequiredDecoratorTest(BaseTestMixin, TestCase):
    """Test subscription_required decorator"""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.decorated_view = subscription_required(dummy_view)

    def add_middleware_to_request(self, request):
        """Add required middleware to request""" 
        middleware = SessionMiddleware(get_response=lambda r: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def test_subscription_required_anonymous_user(self):
        """Test decorator redirects anonymous user to login"""
        request = self.factory.get('/')
        request.user = AnonymousUser()
        request = self.add_middleware_to_request(request)
        
        response = self.decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_subscription_required_user_with_active_subscription(self):
        """Test decorator allows user with active subscription"""
        self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = self.decorated_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Success")

    def test_subscription_required_user_without_subscription(self):
        """Test decorator redirects user without subscription"""
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = self.decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need an active subscription', str(messages[0]))

    def test_subscription_required_user_with_expired_subscription(self):
        """Test decorator redirects user with expired subscription"""
        past_date = timezone.now() - timedelta(days=1)
        self.create_subscription(
            expiry_date=past_date
        )
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = self.decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need an active subscription', str(messages[0]))

    def test_subscription_required_user_with_cancelled_subscription(self):
        """Test decorator redirects user with cancelled subscription"""
        self.create_subscription(
            status='cancelled'
        )
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = self.decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need an active subscription', str(messages[0]))

    def test_subscription_required_preserves_function_metadata(self):
        """Test decorator preserves original function metadata"""
        def test_view(request):
            """Test view docstring"""
            return HttpResponse("Test")
        
        decorated = subscription_required(test_view)
        
        self.assertEqual(decorated.__name__, test_view.__name__)
        self.assertEqual(decorated.__doc__, test_view.__doc__)

    def test_subscription_required_with_args_and_kwargs(self):
        """Test decorator works with view args and kwargs"""
        def view_with_args(request, arg1, kwarg1=None):
            return HttpResponse(f"Args: {arg1}, {kwarg1}")
        
        decorated_view = subscription_required(view_with_args)
        self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request, "test_arg", kwarg1="test_kwarg")
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("test_arg", response.content.decode())
        self.assertIn("test_kwarg", response.content.decode())


class PlanRequiredDecoratorTest(BaseTestMixin, TestCase):
    """Test plan_required decorator"""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def add_middleware_to_request(self, request):
        """Add required middleware to request"""
        middleware = SessionMiddleware(get_response=lambda r: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def test_plan_required_anonymous_user(self):
        """Test decorator redirects anonymous user to login"""
        decorated_view = plan_required('Basic Plan')(dummy_view)
        
        request = self.factory.get('/')
        request.user = AnonymousUser()
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

    def test_plan_required_user_with_correct_plan(self):
        """Test decorator allows user with correct plan"""
        self.create_subscription(plan=self.basic_plan)
        decorated_view = plan_required('Basic Plan')(dummy_view)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Success")

    def test_plan_required_user_with_wrong_plan(self):
        """Test decorator redirects user with wrong plan"""
        self.create_subscription(plan=self.basic_plan)
        decorated_view = plan_required('Premium Plan')(dummy_view)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need the Premium Plan', str(messages[0]))

    def test_plan_required_user_without_subscription(self):
        """Test decorator redirects user without any subscription"""
        decorated_view = plan_required('Basic Plan')(dummy_view)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need the Basic Plan', str(messages[0]))

    def test_plan_required_user_with_expired_subscription(self):
        """Test decorator redirects user with expired subscription of correct plan"""
        past_date = timezone.now() - timedelta(days=1)
        self.create_subscription(
            plan=self.basic_plan,
            expiry_date=past_date
        )
        decorated_view = plan_required('Basic Plan')(dummy_view)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need the Basic Plan', str(messages[0]))

    def test_plan_required_business_plan(self):
        """Test plan_required with Business Member Plan"""
        self.create_subscription(plan=self.business_plan)
        decorated_view = plan_required('Business Member Plan')(dummy_view)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Success")

    def test_plan_required_case_sensitivity(self):
        """Test plan_required is case sensitive"""
        self.create_subscription(plan=self.basic_plan)
        decorated_view = plan_required('basic plan')(dummy_view)  # lowercase
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)

    def test_plan_required_preserves_function_metadata(self):
        """Test plan_required preserves original function metadata"""
        def test_view(request):
            """Test view docstring"""
            return HttpResponse("Test")
        
        decorated = plan_required('Basic Plan')(test_view)
        
        self.assertEqual(decorated.__name__, test_view.__name__)
        self.assertEqual(decorated.__doc__, test_view.__doc__)

    def test_plan_required_with_args_and_kwargs(self):
        """Test plan_required works with view args and kwargs"""
        def view_with_args(request, arg1, kwarg1=None):
            return HttpResponse(f"Args: {arg1}, {kwarg1}")
        
        self.create_subscription(plan=self.basic_plan)
        decorated_view = plan_required('Basic Plan')(view_with_args)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request, "test_arg", kwarg1="test_kwarg")
        
        self.assertEqual(response.status_code, 200)
        self.assertIn("test_arg", response.content.decode())
        self.assertIn("test_kwarg", response.content.decode())

    def test_multiple_plan_requirements(self):
        """Test applying plan_required multiple times (edge case)"""
        self.create_subscription(plan=self.basic_plan)
        
        # This would be unusual but let's test it doesn't break
        decorated_view = plan_required('Basic Plan')(
            plan_required('Basic Plan')(dummy_view)
        )
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Success")

    def test_plan_required_nonexistent_plan(self):
        """Test plan_required with nonexistent plan name"""
        self.create_subscription(plan=self.basic_plan)
        decorated_view = plan_required('Nonexistent Plan')(dummy_view)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = decorated_view(request)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/subscriptions/', response.url)
        
        # Check warning message was added
        messages = list(get_messages(request))
        self.assertEqual(len(messages), 1)
        self.assertIn('need the Nonexistent Plan', str(messages[0]))


class DecoratorIntegrationTest(BaseTestMixin, TestCase):
    """Test decorators in integration scenarios"""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()

    def add_middleware_to_request(self, request):
        """Add required middleware to request"""
        middleware = SessionMiddleware(get_response=lambda r: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def test_decorators_stacked_subscription_and_plan(self):
        """Test stacking both decorators"""
        @subscription_required
        @plan_required('Basic Plan')
        def stacked_view(request):
            return HttpResponse("Stacked Success")
        
        self.create_subscription(plan=self.basic_plan)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = stacked_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Stacked Success")

    def test_decorators_stacked_wrong_order(self):
        """Test stacking decorators in different order"""
        @plan_required('Basic Plan')
        @subscription_required
        def stacked_view(request):
            return HttpResponse("Stacked Success")
        
        self.create_subscription(plan=self.basic_plan)
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = stacked_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Stacked Success")

    def test_decorators_with_login_required(self):
        """Test compatibility with Django's login_required decorator"""
        from django.contrib.auth.decorators import login_required
        
        @login_required
        @subscription_required
        def protected_view(request):
            return HttpResponse("Protected Success")
        
        self.create_subscription()
        
        request = self.factory.get('/')
        request.user = self.user
        request = self.add_middleware_to_request(request)
        
        response = protected_view(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), "Protected Success")

        from unittest.mock import patch

        def test_decorator_error_handling(self):
            """Test decorator behavior when SubscriptionService fails"""
            request = self.factory.get('/')
            request.user = self.user
            request = self.add_middleware_to_request(request)
            
            decorated_view = subscription_required(dummy_view)
            
            with patch('subscriptions.services.SubscriptionService.get_user_active_subscription') as mock_service:
                mock_service.side_effect = Exception("Service failure")
                
                with self.assertRaises(Exception):
                    decorated_view(request)
