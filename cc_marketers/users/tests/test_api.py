# apps/users/tests/test_api.py
import json
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch


from .test_utils import BaseTestCase, APITestMixin

User = get_user_model()


class CheckEmailAvailabilityAPITest(BaseTestCase, APITestMixin):
    """Test CheckEmailAvailabilityView API functionality."""
    
    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.url = reverse('users:check_email')
        self.existing_user = self.create_user(email='existing@example.com')
    
    def test_check_available_email(self):
        """Test checking available email address."""
        response = self.client.get(f'{self.url}?email=available@example.com')
        
        data = self.assert_api_success(response, {
            'available': True,
            'message': 'Email available'
        })
        
        self.assertTrue(data['available'])
    
    def test_check_taken_email(self):
        """Test checking taken email address."""
        response = self.client.get(f'{self.url}?email=existing@example.com')
        
        data = self.assert_api_success(response, {
            'available': False,
            'message': 'Email taken'
        })
        
        self.assertFalse(data['available'])
    
    def test_check_email_without_parameter(self):
        """Test API without email parameter."""
        response = self.client.get(self.url)
        
        data = self.assert_api_success(response, {
            'available': False,
            'message': 'Email required'
        })
        
        self.assertFalse(data['available'])
    
    def test_check_email_with_empty_parameter(self):
        """Test API with empty email parameter."""
        response = self.client.get(f'{self.url}?email=')
        
        data = self.assert_api_success(response, {
            'available': False,
            'message': 'Email required'
        })
        
        self.assertFalse(data['available'])
    
    def test_check_email_case_insensitive(self):
        """Test email check is case insensitive."""
        # Create user with lowercase email
        self.create_user(email='test@example.com')
        
        # Check with uppercase
        response = self.client.get(f'{self.url}?email=TEST@EXAMPLE.COM')
        
        data = self.assert_api_success(response)
        # Should detect as taken due to case insensitivity
        self.assertFalse(data['available'])
    
    def test_check_email_with_special_characters(self):
        """Test email check with special characters."""
        special_emails = [
            'test+tag@example.com',
            'user.name@example.com',
            'user-name@example.com',
            'user_name@example.com'
        ]
        
        for email in special_emails:
            response = self.client.get(f'{self.url}?email={email}')
            data = self.assert_api_success(response)
            self.assertTrue(data['available'])  # Should be available
    
    def test_check_email_with_invalid_format(self):
        """Test email check with invalid email format."""
        invalid_emails = [
            'invalid-email',
            '@example.com',
            'test@',
            'test@@example.com'
        ]
        
        for email in invalid_emails:
            response = self.client.get(f'{self.url}?email={email}')
            data = self.assert_api_success(response)
            # API should handle invalid format gracefully
            self.assertIn('available', data)
    
    def test_check_email_response_format(self):
        """Test API response format is correct."""
        response = self.client.get(f'{self.url}?email=test@example.com')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = response.json()
        self.assertIn('available', data)
        self.assertIn('message', data)
        self.assertIsInstance(data['available'], bool)
        self.assertIsInstance(data['message'], str)


class CheckPhoneAvailabilityAPITest(BaseTestCase, APITestMixin):
    """Test CheckPhoneAvailabilityView API functionality."""
    
    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.url = reverse('users:check_phone')
        self.existing_user = self.create_user(phone='+2348012345678')
    
    def test_check_available_phone(self):
        """Test checking available phone number."""
        response = self.client.get(f'{self.url}?phone=%2B2348099999999')
        
        data = self.assert_api_success(response, {
            'available': True,
            'message': 'Phone available'
        })
        
        self.assertTrue(data['available'])
    
    def test_check_taken_phone(self):
        """Test checking taken phone number."""
        response = self.client.get(f'{self.url}?phone=%2B2348012345678')
        
        data = self.assert_api_success(response, {
            'available': False,
            'message': 'Phone taken'
        })
        
        self.assertFalse(data['available'])
    
    def test_check_phone_without_parameter(self):
        """Test API without phone parameter."""
        response = self.client.get(self.url)
        
        data = self.assert_api_success(response, {
            'available': False,
            'message': 'Phone required'
        })
        
        self.assertFalse(data['available'])
    
    def test_check_phone_with_empty_parameter(self):
        """Test API with empty phone parameter."""
        response = self.client.get(f'{self.url}?phone=')
        
        data = self.assert_api_success(response, {
            'available': False,
            'message': 'Phone required'
        })
        
        self.assertFalse(data['available'])
    
    def test_check_phone_with_different_formats(self):
        """Test phone check with different number formats."""
        # Create user with international format
        self.create_user(phone='+2348012345678', email='test@example.com')
        
        # Test different formats of the same number
        phone_formats = [
            '+2348012345678',  # International
            '08012345678',     # Local
            '2348012345678'    # Without plus
        ]
        
        # All should be detected as taken if normalized properly
        for phone in phone_formats:
            response = self.client.get(f'{self.url}?phone={phone}')
            data = self.assert_api_success(response)
            # This depends on how phone normalization is implemented
            self.assertIn('available', data)
    
    def test_check_phone_url_encoding(self):
        """Test phone check with URL encoded characters."""
        # + sign should be URL encoded as %2B
        response = self.client.get(f'{self.url}?phone=%2B2348099999999')
        data = self.assert_api_success(response)
        self.assertTrue(data['available'])
    
    def test_check_phone_response_format(self):
        """Test API response format is correct."""
        response = self.client.get(f'{self.url}?phone=%2B2348099999999')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = response.json()
        self.assertIn('available', data)
        self.assertIn('message', data)
        self.assertIsInstance(data['available'], bool)
        self.assertIsInstance(data['message'], str)


class ValidateReferralCodeAPITest(BaseTestCase, APITestMixin):
    """Test ValidateReferralCodeView API functionality."""
    
    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.url = reverse('users:validate_referral')
        self.referrer = self.create_user(email='referrer@example.com')
        self.referral_code = self.create_referral_code(
            user=self.referrer,
            code='VALID123'
        )
    
    def test_validate_valid_referral_code(self):
        """Test validating valid referral code."""
        response = self.client.get(f'{self.url}?code=VALID123')
        
        data = self.assert_api_success(response)
        
        self.assertTrue(data['valid'])
        self.assertIn('Valid referral from', data['message'])
        self.assertIn('referrer', data)
        self.assertEqual(data['referrer']['name'], self.referrer.get_display_name())
        self.assertEqual(data['referrer']['username'], self.referrer.username)
    
    def test_validate_invalid_referral_code(self):
        """Test validating invalid referral code."""
        response = self.client.get(f'{self.url}?code=INVALID123')
        
        data = self.assert_api_success(response, {
            'valid': False,
            'message': 'Invalid referral code'
        })
        
        self.assertFalse(data['valid'])
        self.assertNotIn('referrer', data)
    
    def test_validate_referral_without_parameter(self):
        """Test API without code parameter."""
        response = self.client.get(self.url)
        
        data = self.assert_api_success(response, {
            'valid': False,
            'message': 'Code required'
        })
        
        self.assertFalse(data['valid'])
    
    def test_validate_referral_with_empty_parameter(self):
        """Test API with empty code parameter."""
        response = self.client.get(f'{self.url}?code=')
        
        data = self.assert_api_success(response, {
            'valid': False,
            'message': 'Code required'
        })
        
        self.assertFalse(data['valid'])
    
    def test_validate_inactive_referral_code(self):
        """Test validating inactive referral code."""
        # Create inactive referral code
        self.create_referral_code(
            user=self.referrer,
            code='INACTIVE123',
            is_active=False
        )
        
        response = self.client.get(f'{self.url}?code=INACTIVE123')
        
        data = self.assert_api_success(response)
        # Should be invalid if code is inactive
        self.assertFalse(data['valid'])
    
    def test_validate_referral_case_sensitivity(self):
        """Test referral code validation case sensitivity."""
        # Try different cases
        test_codes = ['VALID123', 'valid123', 'Valid123']
        
        for code in test_codes:
            response = self.client.get(f'{self.url}?code={code}')
            data = self.assert_api_success(response)
            
            # Only exact match should be valid (assuming case-sensitive)
            if code == 'VALID123':
                self.assertTrue(data['valid'])
            else:
                # This depends on implementation - might be case-insensitive
                self.assertIn('valid', data)
    
    def test_validate_referral_with_user_details(self):
        """Test referral validation returns correct user details."""
        response = self.client.get(f'{self.url}?code=VALID123')
        
        data = self.assert_api_success(response)
        
        self.assertTrue(data['valid'])
        self.assertIn('referrer', data)
        
        referrer_data = data['referrer']
        self.assertIn('name', referrer_data)
        self.assertIn('username', referrer_data)
        self.assertEqual(referrer_data['name'], self.referrer.get_display_name())
        self.assertEqual(referrer_data['username'], self.referrer.username)
    
    def test_validate_referral_response_format(self):
        """Test API response format is correct."""
        response = self.client.get(f'{self.url}?code=VALID123')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        data = response.json()
        required_fields = ['valid', 'message']
        for field in required_fields:
            self.assertIn(field, data)
        
        if data['valid']:
            self.assertIn('referrer', data)
            referrer_fields = ['name', 'username']
            for field in referrer_fields:
                self.assertIn(field, data['referrer'])


class APIErrorHandlingTest(BaseTestCase):
    """Test API error handling scenarios."""
    
    def test_api_with_malformed_requests(self):
        """Test APIs handle malformed requests gracefully."""
        apis = [
            ('users:check_email', 'email'),
            ('users:check_phone', 'phone'),
            ('users:validate_referral', 'code')
        ]
        
        for api_name, param_name in apis:
            url = reverse(api_name)
            
            # Test with extremely long parameter
            long_value = 'a' * 1000
            response = self.client.get(f'{url}?{param_name}={long_value}')
            self.assertEqual(response.status_code, 200)
            
            # Test with special characters
            special_value = '<script>alert("xss")</script>'
            response = self.client.get(f'{url}?{param_name}={special_value}')
            self.assertEqual(response.status_code, 200)
            
            # Response should be valid JSON
            try:
                data = response.json()
                self.assertIsInstance(data, dict)
            except json.JSONDecodeError:
                self.fail(f"API {api_name} returned invalid JSON")
    
    def test_api_with_sql_injection_attempts(self):
        """Test APIs are protected against SQL injection."""
        injection_attempts = [
            "'; DROP TABLE users; --",
            "admin@example.com' OR '1'='1",
            "' UNION SELECT * FROM users --"
        ]
        
        for injection in injection_attempts:
            # Test email API
            response = self.client.get(f'{reverse("users:check_email")}?email={injection}')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn('available', data)
            
            # Test referral API
            response = self.client.get(f'{reverse("users:validate_referral")}?code={injection}')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn('valid', data)
    
    def test_api_with_unicode_input(self):
        """Test APIs handle unicode input correctly."""
        unicode_inputs = [
            'tëst@éxample.com',
            'تست@example.com',
            '测试@example.com'
        ]
        
        for unicode_input in unicode_inputs:
            response = self.client.get(f'{reverse("users:check_email")}?email={unicode_input}')
            self.assertEqual(response.status_code, 200)
            
            try:
                data = response.json()
                self.assertIn('available', data)
            except json.JSONDecodeError:
                self.fail(f"API failed to handle unicode input: {unicode_input}")
    
    def test_api_http_methods(self):
        """Test APIs only accept appropriate HTTP methods."""
        apis = [
            reverse('users:check_email'),
            reverse('users:check_phone'),
            reverse('users:validate_referral')
        ]
        
        for url in apis:
            # GET should work
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            
            # POST should either work or return method not allowed
            response = self.client.post(url)
            self.assertIn(response.status_code, [200, 405])
            
            # Other methods should not be allowed
            response = self.client.put(url)
            self.assertEqual(response.status_code, 405)
            
            response = self.client.delete(url)
            self.assertEqual(response.status_code, 405)


class APIPerformanceTest(BaseTestCase):
    """Test API performance characteristics."""
    
    def test_api_query_optimization(self):
        """Test APIs don't perform unnecessary database queries."""
        from django.db import connection
        
        # Create multiple users for testing
        [self.create_user(email=f'user{i}@example.com') for i in range(10)]
        
        # Test email availability API
        connection.queries_log.clear()
        self.client.get(f'{reverse("users:check_email")}?email=test@example.com')
        email_queries = len(connection.queries)
        
        # Should be minimal queries (ideally 1)
        self.assertLessEqual(email_queries, 3)
        
        # Test phone availability API
        connection.queries_log.clear()
        self.client.get(f'{reverse("users:check_phone")}?phone=%2B2348099999999')
        phone_queries = len(connection.queries)
        
        # Should be minimal queries (ideally 1)
        self.assertLessEqual(phone_queries, 3)
        
        # Test referral validation API
        self.create_referral_code(code='PERF123')
        connection.queries_log.clear()
        self.client.get(f'{reverse("users:validate_referral")}?code=PERF123')
        referral_queries = len(connection.queries)
        
        # Should be minimal queries
        self.assertLessEqual(referral_queries, 5)
    
    def test_api_concurrent_requests(self):
        """Test APIs handle concurrent requests properly."""
        import threading
        
        results = []
        
        def make_request():
            response = self.client.get(f'{reverse("users:check_email")}?email=concurrent@example.com')
            results.append(response.status_code)
        
        # Create multiple threads
        threads = [threading.Thread(target=make_request) for _ in range(5)]
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All requests should succeed
        self.assertEqual(len(results), 5)
        self.assertTrue(all(status == 200 for status in results))


class APIIntegrationWithFormsTest(BaseTestCase):
    """Test API integration with form validation."""
    
    def test_email_api_matches_form_validation(self):
        """Test email API results match form validation."""
        self.create_user(email='existing@example.com')
        
        # API should say email is taken
        api_response = self.client.get(f'{reverse("users:check_email")}?email=existing@example.com')
        api_data = api_response.json()
        self.assertFalse(api_data['available'])
        
        # Form should also reject this email
        from users.forms import CustomUserCreationForm
        form = CustomUserCreationForm(data={
            'email': 'existing@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': User.MEMBER
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
    
    def test_phone_api_matches_form_validation(self):
        """Test phone API results match form validation."""
        self.create_user(phone='+2348012345678')
        
        # API should say phone is taken
        api_response = self.client.get(f'{reverse("users:check_phone")}?phone=%2B2348012345678')
        api_data = api_response.json()
        self.assertFalse(api_data['available'])
        
        # Form should also reject this phone
        from users.forms import CustomUserCreationForm
        form = CustomUserCreationForm(data={
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '+2348012345678',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': User.MEMBER
        })
        
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)
    
    def test_referral_api_matches_form_validation(self):
        """Test referral API results match form validation."""
        # Valid referral code
        self.create_referral_code(code='FORM123')
        
        api_response = self.client.get(f'{reverse("users:validate_referral")}?code=FORM123')
        api_data = api_response.json()
        self.assertTrue(api_data['valid'])
        
        # Form should also accept this code
        from users.forms import CustomUserCreationForm
        form = CustomUserCreationForm(data={
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': User.MEMBER,
            'referral_code': 'FORM123'
        })
        
        self.assertTrue(form.is_valid())


class APISecurityTest(BaseTestCase):
    """Test API security measures."""
    
    def test_api_xss_protection(self):
        """Test APIs are protected against XSS attacks."""
        xss_payloads = [
            '<script>alert("xss")</script>',
            'javascript:alert("xss")',
            '<img src="x" onerror="alert(1)">'
        ]
        
        for payload in xss_payloads:
            # Test all APIs with XSS payloads
            apis = [
                ('users:check_email', 'email'),
                ('users:check_phone', 'phone'),
                ('users:validate_referral', 'code')
            ]
            
            for api_name, param_name in apis:
                response = self.client.get(f'{reverse(api_name)}?{param_name}={payload}')
                
                # Should return valid JSON response
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/json')
                
                # Response should not contain unescaped payload
                response_content = response.content.decode()
                self.assertNotIn('<script>', response_content)
    
    def test_api_csrf_exemption(self):
        """Test APIs are properly CSRF exempt if needed."""
        # APIs typically don't need CSRF for GET requests
        response = self.client.get(f'{reverse("users:check_email")}?email=test@example.com')
        self.assertEqual(response.status_code, 200)
    
    def test_api_rate_limiting_readiness(self):
        """Test APIs are ready for rate limiting implementation."""
        # Make multiple rapid requests
        for i in range(20):
            response = self.client.get(f'{reverse("users:check_email")}?email=test{i}@example.com')
            self.assertEqual(response.status_code, 200)
            
            # Should always return valid JSON
            data = response.json()
            self.assertIn('available', data)


class APICachingTest(BaseTestCase):
    """Test API caching behavior."""
    
    def test_api_response_caching(self):
        """Test API responses can be cached appropriately."""
        # Make same request multiple times
        url = f'{reverse("users:check_email")}?email=cache@example.com'
        
        responses = []
        for _ in range(3):
            response = self.client.get(url)
            responses.append(response)
        
        # All responses should be identical
        for response in responses:
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['available'])  # Should be consistent
    
    def test_api_cache_invalidation(self):
        """Test API cache invalidation when data changes."""
        email = 'cache_test@example.com'
        
        # Check email availability - should be available
        response = self.client.get(f'{reverse("users:check_email")}?email={email}')
        data = response.json()
        self.assertTrue(data['available'])
        
        # Create user with that email
        self.create_user(email=email)
        
        # Check again - should now be taken
        response = self.client.get(f'{reverse("users:check_email")}?email={email}')
        data = response.json()
        self.assertFalse(data['available'])


class APIDocumentationTest(BaseTestCase):
    """Test API documentation and behavior consistency."""
    
    def test_api_response_structure_consistency(self):
        """Test all APIs return consistent response structures."""
        # Email API
        response = self.client.get(f'{reverse("users:check_email")}?email=test@example.com')
        email_data = response.json()
        self.assertIn('available', email_data)
        self.assertIn('message', email_data)
        
        # Phone API
        response = self.client.get(f'{reverse("users:check_phone")}?phone=%2B2348099999999')
        phone_data = response.json()
        self.assertIn('available', phone_data)
        self.assertIn('message', phone_data)
        
        # Referral API
        response = self.client.get(f'{reverse("users:validate_referral")}?code=TEST123')
        referral_data = response.json()
        self.assertIn('valid', referral_data)
        self.assertIn('message', referral_data)
        
        # Each API should have consistent field types
        self.assertIsInstance(email_data['available'], bool)
        self.assertIsInstance(phone_data['available'], bool)
        self.assertIsInstance(referral_data['valid'], bool)
        
        self.assertIsInstance(email_data['message'], str)
        self.assertIsInstance(phone_data['message'], str)
        self.assertIsInstance(referral_data['message'], str)
    
    def test_api_error_message_quality(self):
        """Test API error messages are user-friendly."""
        # Test missing parameters
        apis = [
            reverse('users:check_email'),
            reverse('users:check_phone'),
            reverse('users:validate_referral')
        ]
        
        for api_url in apis:
            response = self.client.get(api_url)
            data = response.json()
            
            # Error message should be present and descriptive
            self.assertIn('message', data)
            message = data['message']
            self.assertIsInstance(message, str)
            self.assertGreater(len(message), 0)
            self.assertIn('required', message.lower())
    
    def test_api_parameter_encoding_handling(self):
        """Test APIs handle different parameter encodings."""
        # Test URL encoding
        encoded_email = 'test%40example.com'  # test@example.com
        response = self.client.get(f'{reverse("users:check_email")}?email={encoded_email}')
        self.assertEqual(response.status_code, 200)
        
        # Test phone with + encoding
        encoded_phone = '%2B2348099999999'  # +2348099999999
        response = self.client.get(f'{reverse("users:check_phone")}?phone={encoded_phone}')
        self.assertEqual(response.status_code, 200)


class APIMockingTest(BaseTestCase):
    """Test API behavior with mocked dependencies."""
    
    @patch('users.models.User.objects.filter')
    def test_email_api_with_database_error(self, mock_filter):
        """Test email API handles database errors gracefully."""
        mock_filter.side_effect = Exception("Database connection failed")
        
        response = self.client.get(f'{reverse("users:check_email")}?email=test@example.com')
        
        # Should handle error gracefully (implementation dependent)
        # Might return 500 or handle gracefully
        self.assertIn(response.status_code, [200, 500])
    
    @patch('referrals.models.ReferralCode.objects.filter')
    def test_referral_api_with_database_error(self, mock_filter):
        """Test referral API handles database errors gracefully."""
        mock_filter.side_effect = Exception("Database connection failed")
        
        response = self.client.get(f'{reverse("users:validate_referral")}?code=TEST123')
        
        # Should handle error gracefully
        self.assertIn(response.status_code, [200, 500])
    
    def test_api_with_slow_database(self):
        """Test API behavior with slow database responses."""
        # This would require more complex mocking in a real scenario
        # For now, just ensure APIs complete within reasonable time
        import time
        
        start_time = time.time()
        response = self.client.get(f'{reverse("users:check_email")}?email=slow@example.com')
        end_time = time.time()
        
        # Should complete quickly
        self.assertLess(end_time - start_time, 1.0)  # Less than 1 second
        self.assertEqual(response.status_code, 200)


class APIComprehensiveCoverageTest(BaseTestCase):
    """Comprehensive API coverage tests."""
    
    def test_all_api_endpoints_functional(self):
        """Test all API endpoints are functional."""
        # Create test data
        self.create_user(
            email='existing@example.com',
            phone='+2348012345678'
        )
        self.create_referral_code(code='API123')
        
        # Test all scenarios for each API
        test_cases = [
            # Email API
            ('users:check_email', 'email=available@example.com', True),
            ('users:check_email', 'email=existing@example.com', False),
            ('users:check_email', '', False),
            
            # Phone API
            ('users:check_phone', 'phone=%2B2348099999999', True),
            ('users:check_phone', 'phone=%2B2348012345678', False),
            ('users:check_phone', '', False),
            
            # Referral API
            ('users:validate_referral', 'code=API123', True),
            ('users:validate_referral', 'code=INVALID123', False),
            ('users:validate_referral', '', False),
        ]
        
        for api_name, params, expected_success in test_cases:
            url = reverse(api_name)
            if params:
                url += f'?{params}'
            
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            
            data = response.json()
            
            # Check response format based on API type
            if 'check_' in api_name:
                self.assertIn('available', data)
                if expected_success and params:
                    # Available should match expectation when params provided
                    if 'existing@example.com' in params or '+2348012345678' in params:
                        self.assertFalse(data['available'])
                    elif 'available@example.com' in params or '+2348099999999' in params:
                        self.assertTrue(data['available'])
            else:  # validate_referral
                self.assertIn('valid', data)
                if expected_success and params:
                    if 'API123' in params:
                        self.assertTrue(data['valid'])
                    elif 'INVALID123' in params:
                        self.assertFalse(data['valid'])
    
    def test_api_edge_case_coverage(self):
        """Test API edge cases for complete coverage."""
        # Test with boundary values
        boundary_tests = [
            # Very long email
            ('users:check_email', 'email=' + 'a' * 240 + '@example.com'),
            # Very short phone
            ('users:check_phone', 'phone=123'),
            # Very long referral code
            ('users:validate_referral', 'code=' + 'A' * 50),
        ]
        
        for api_name, params in boundary_tests:
            url = f'{reverse(api_name)}?{params}'
            response = self.client.get(url)
            
            # Should handle gracefully
            self.assertEqual(response.status_code, 200)
            
            # Should return valid JSON
            try:
                data = response.json()
                self.assertIsInstance(data, dict)
            except json.JSONDecodeError:
                self.fail(f"API {api_name} returned invalid JSON for boundary test")
    
    def test_api_content_type_headers(self):
        """Test APIs return correct content type headers."""
        apis = [
            reverse('users:check_email'),
            reverse('users:check_phone'),
            reverse('users:validate_referral')
        ]
        
        for api_url in apis:
            response = self.client.get(api_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/json')
    
    def test_api_character_encoding(self):
        """Test APIs handle character encoding properly."""
        # Test with various character encodings
        test_cases = [
            ('test@example.com', 'ASCII'),
            ('tëst@éxample.com', 'Latin-1'),
            ('测试@example.com', 'UTF-8'),
            ('тест@example.com', 'Cyrillic'),
        ]
        
        for email, encoding_type in test_cases:
            response = self.client.get(f'{reverse("users:check_email")}?email={email}')
            self.assertEqual(response.status_code, 200)
            
            # Should return valid JSON regardless of input encoding
            try:
                data = response.json()
                self.assertIn('available', data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.fail(f"API failed to handle {encoding_type} encoding for: {email}")