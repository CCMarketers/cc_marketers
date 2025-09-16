# tests/test_urls.py
from django.test import TestCase
from django.urls import reverse, resolve
from django.http import Http404

from subscriptions import views


class SubscriptionUrlsTest(TestCase):
    """Test subscription URL configurations"""

    def test_plans_url_name_resolves(self):
        """Test subscriptions:plans URL name resolves correctly"""
        url = reverse('subscriptions:plans')
        self.assertEqual(url, '/subscriptions/')

    def test_plans_url_resolves_to_correct_view(self):
        """Test plans URL resolves to correct view function"""
        resolver = resolve('/subscriptions/')
        self.assertEqual(resolver.func, views.subscription_plans)
        self.assertEqual(resolver.app_name, 'subscriptions')
        self.assertEqual(resolver.url_name, 'plans')

    def test_subscribe_url_name_resolves(self):
        """Test subscriptions:subscribe URL name resolves correctly"""
        url = reverse('subscriptions:subscribe', args=[1])
        self.assertEqual(url, '/subscriptions/subscribe/1/')

    def test_subscribe_url_resolves_to_correct_view(self):
        """Test subscribe URL resolves to correct view function"""
        resolver = resolve('/subscriptions/subscribe/1/')
        self.assertEqual(resolver.func, views.subscribe)
        self.assertEqual(resolver.app_name, 'subscriptions')
        self.assertEqual(resolver.url_name, 'subscribe')
        self.assertEqual(resolver.kwargs, {'plan_id': 1})

    def test_subscribe_url_with_different_plan_ids(self):
        """Test subscribe URL works with different plan IDs"""
        test_plan_ids = [1, 5, 10, 100, 999]
        
        for plan_id in test_plan_ids:
            with self.subTest(plan_id=plan_id):
                url = reverse('subscriptions:subscribe', args=[plan_id])
                resolver = resolve(url)
                
                self.assertEqual(resolver.func, views.subscribe)
                self.assertEqual(resolver.kwargs, {'plan_id': plan_id})

    def test_my_subscription_url_name_resolves(self):
        """Test subscriptions:my_subscription URL name resolves correctly"""
        url = reverse('subscriptions:my_subscription')
        self.assertEqual(url, '/subscriptions/my-subscription/')

    def test_my_subscription_url_resolves_to_correct_view(self):
        """Test my_subscription URL resolves to correct view function"""
        resolver = resolve('/subscriptions/my-subscription/')
        self.assertEqual(resolver.func, views.my_subscription)
        self.assertEqual(resolver.app_name, 'subscriptions')
        self.assertEqual(resolver.url_name, 'my_subscription')

    def test_toggle_auto_renewal_url_name_resolves(self):
        """Test subscriptions:toggle_auto_renewal URL name resolves correctly"""
        url = reverse('subscriptions:toggle_auto_renewal')
        self.assertEqual(url, '/subscriptions/toggle-auto-renewal/')

    def test_toggle_auto_renewal_url_resolves_to_correct_view(self):
        """Test toggle_auto_renewal URL resolves to correct view function"""
        resolver = resolve('/subscriptions/toggle-auto-renewal/')
        self.assertEqual(resolver.func, views.toggle_auto_renewal)
        self.assertEqual(resolver.app_name, 'subscriptions')
        self.assertEqual(resolver.url_name, 'toggle_auto_renewal')

    def test_cancel_subscription_url_name_resolves(self):
        """Test subscriptions:cancel_subscription URL name resolves correctly"""
        url = reverse('subscriptions:cancel_subscription')
        self.assertEqual(url, '/subscriptions/cancel/')

    def test_cancel_subscription_url_resolves_to_correct_view(self):
        """Test cancel URL resolves to correct view function"""
        resolver = resolve('/subscriptions/cancel/')
        self.assertEqual(resolver.func, views.cancel_subscription)
        self.assertEqual(resolver.app_name, 'subscriptions')
        self.assertEqual(resolver.url_name, 'cancel_subscription')

    def test_all_urls_have_correct_app_name(self):
        """Test all URLs have correct app name"""
        url_names = [
            'plans',
            'subscribe',
            'my_subscription',
            'toggle_auto_renewal',
            'cancel_subscription'
        ]
        
        for url_name in url_names:
            with self.subTest(url_name=url_name):
                if url_name == 'subscribe':
                    # Subscribe needs an argument
                    url = reverse(f'subscriptions:{url_name}', args=[1])
                    resolver = resolve(url)
                else:
                    url = reverse(f'subscriptions:{url_name}')
                    resolver = resolve(url)
                
                self.assertEqual(resolver.app_name, 'subscriptions')
                self.assertEqual(resolver.url_name, url_name)

    def test_subscribe_url_integer_parameter_only(self):
        """Test subscribe URL only accepts integer parameters"""
        # Valid integer URLs
        valid_urls = [
            '/subscriptions/subscribe/1/',
            '/subscriptions/subscribe/123/',
            '/subscriptions/subscribe/999/'
        ]
        
        for url in valid_urls:
            with self.subTest(url=url):
                try:
                    resolver = resolve(url)
                    self.assertEqual(resolver.func, views.subscribe)
                except Http404:
                    self.fail(f"Valid URL {url} should resolve")

    def test_subscribe_url_invalid_parameters(self):
        """Test subscribe URL rejects invalid parameters"""
        # Invalid URLs that should not resolve
        invalid_urls = [
            '/subscriptions/subscribe/abc/',
            '/subscriptions/subscribe/1.5/',
            '/subscriptions/subscribe/-1/',
            '/subscriptions/subscribe/1/extra/',
            '/subscriptions/subscribe/'
        ]
        
        for url in invalid_urls:
            with self.subTest(url=url):
                with self.assertRaises(Http404):
                    resolve(url)

    def test_url_patterns_order(self):
        """Test URL patterns don't conflict with each other"""
        # Test that more specific patterns come before general ones
        
        # These should all resolve to different views
        test_cases = [
            ('/subscriptions/', views.subscription_plans),
            ('/subscriptions/subscribe/1/', views.subscribe),
            ('/subscriptions/my-subscription/', views.my_subscription),
            ('/subscriptions/toggle-auto-renewal/', views.toggle_auto_renewal),
            ('/subscriptions/cancel/', views.cancel_subscription),
        ]
        
        for url, expected_view in test_cases:
            with self.subTest(url=url):
                resolver = resolve(url)
                self.assertEqual(resolver.func, expected_view)

    def test_url_trailing_slashes(self):
        """Test URL patterns handle trailing slashes correctly"""
        # All subscription URLs should end with trailing slashes
        url_patterns = [
            ('subscriptions:plans', [], '/subscriptions/'),
            ('subscriptions:subscribe', [1], '/subscriptions/subscribe/1/'),
            ('subscriptions:my_subscription', [], '/subscriptions/my-subscription/'),
            ('subscriptions:toggle_auto_renewal', [], '/subscriptions/toggle-auto-renewal/'),
            ('subscriptions:cancel_subscription', [], '/subscriptions/cancel/'),
        ]
        
        for url_name, args, expected_url in url_patterns:
            with self.subTest(url_name=url_name):
                url = reverse(url_name, args=args)
                self.assertEqual(url, expected_url)
                self.assertTrue(url.endswith('/'))

    def test_reverse_url_generation(self):
        """Test reverse URL generation works for all patterns"""
        # Test reverse URL generation doesn't raise exceptions
        try:
            reverse('subscriptions:plans')
            reverse('subscriptions:subscribe', args=[1])
            reverse('subscriptions:my_subscription')
            reverse('subscriptions:toggle_auto_renewal')
            reverse('subscriptions:cancel_subscription')
        except Exception as e:
            self.fail(f"Reverse URL generation failed: {e}")

    def test_url_namespace_consistency(self):
        """Test URL namespace is consistent across all patterns"""
        url_patterns = [
            'subscriptions:plans',
            'subscriptions:subscribe',
            'subscriptions:my_subscription',
            'subscriptions:toggle_auto_renewal',
            'subscriptions:cancel_subscription'
        ]
        
        for pattern in url_patterns:
            with self.subTest(pattern=pattern):
                self.assertTrue(pattern.startswith('subscriptions:'))
                
                # Test the pattern can be reversed
                if 'subscribe' in pattern and pattern != 'subscriptions:my_subscription':
                    url = reverse(pattern, args=[1])
                else:
                    url = reverse(pattern)
                
                self.assertTrue(url.startswith('/subscriptions/'))

    def test_subscribe_url_large_plan_ids(self):
        """Test subscribe URL handles large plan IDs"""
        large_ids = [999999, 1000000, 2147483647]  # Including max int value
        
        for plan_id in large_ids:
            with self.subTest(plan_id=plan_id):
                url = reverse('subscriptions:subscribe', args=[plan_id])
                resolver = resolve(url)
                
                self.assertEqual(resolver.func, views.subscribe)
                self.assertEqual(resolver.kwargs, {'plan_id': plan_id})

    def test_url_pattern_names_are_descriptive(self):
        """Test URL pattern names are descriptive and follow conventions"""
        # Test that URL names follow Django conventions
        url_names = [
            'plans',  # List view
            'subscribe',  # Action view
            'my_subscription',  # Detail view
            'toggle_auto_renewal',  # Action view
            'cancel_subscription'  # Action view
        ]
        
        for url_name in url_names:
            with self.subTest(url_name=url_name):
                # Should not contain underscores at the start/end
                self.assertFalse(url_name.startswith('_'))
                self.assertFalse(url_name.endswith('_'))
                
                # Should be lowercase
                self.assertEqual(url_name, url_name.lower())
                
                # Should be reversible
                if url_name == 'subscribe':
                    url = reverse(f'subscriptions:{url_name}', args=[1])
                else:
                    url = reverse(f'subscriptions:{url_name}')
                self.assertTrue(url.startswith('/subscriptions/'))

    def test_url_regex_security(self):
        """Test URL patterns don't have security issues"""
        # Test that subscribe URL doesn't accept potentially malicious input
        malicious_inputs = [
            '../1',
            '1/../',
            '1%2E%2E%2F',
            '1;DROP TABLE',
            '1<script>',
        ]
        
        for malicious_input in malicious_inputs:
            with self.subTest(input=malicious_input):
                url = f'/subscriptions/subscribe/{malicious_input}/'
                with self.assertRaises(Http404):
                    resolve(url)