# payments/tests/test_api_views.py
import json
from unittest.mock import patch, Mock
from django.urls import reverse

from .test_base import (
    BaseTestCase, PaystackMockMixin, AuthenticationMixin, JSONResponseMixin
)


class GetBanksViewTestCase(BaseTestCase, PaystackMockMixin, AuthenticationMixin, JSONResponseMixin):
    """Test cases for get_banks API view"""
    
    def test_get_banks_unauthenticated(self):
        """Test API requires authentication"""
        self.assert_login_required(self.banks_url, method='GET')
    
    @patch('payments.views.PaystackService')
    def test_get_banks_success(self, mock_paystack_service):
        """Test successful banks retrieval"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.get_banks.return_value = {
            'success': True,
            'data': [
                {'name': 'Access Bank', 'code': '044', 'active': True},
                {'name': 'First Bank', 'code': '011', 'active': True},
                {'name': 'GTB', 'code': '058', 'active': True}
            ]
        }
        
        response = self.authenticated_client.get(self.banks_url)
        
        self.assertJSONSuccess(response, expected_keys=['banks'])
        
        data = response.json()
        self.assertEqual(len(data['banks']), 3)
        self.assertEqual(data['banks'][0]['name'], 'Access Bank')
        self.assertEqual(data['banks'][0]['code'], '044')
        
        # Verify service was called
        mock_service.get_banks.assert_called_once()
    
    @patch('payments.views.PaystackService')
    def test_get_banks_empty_response(self, mock_paystack_service):
        """Test banks API with empty response"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.get_banks.return_value = {
            'success': True,
            'data': []
        }
        
        response = self.authenticated_client.get(self.banks_url)
        
        self.assertJSONSuccess(response, expected_keys=['banks'])
        
        data = response.json()
        self.assertEqual(data['banks'], [])
    
    @patch('payments.views.PaystackService')
    def test_get_banks_service_failure(self, mock_paystack_service):
        """Test banks API when Paystack service fails"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.get_banks.return_value = {
            'success': False,
            'error': 'Network error',
            'data': []
        }
        
        response = self.authenticated_client.get(self.banks_url)
        
        # Should still return 200 with empty banks array
        self.assertJSONSuccess(response, expected_keys=['banks'])
        
        data = response.json()
        self.assertEqual(data['banks'], [])
    
    @patch('payments.views.PaystackService')
    def test_get_banks_service_exception(self, mock_paystack_service):
        """Test banks API when service raises exception"""
        # Setup mock to raise exception
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.get_banks.side_effect = Exception("Connection timeout")
        
        response = self.authenticated_client.get(self.banks_url)
        
        # Should handle gracefully and return empty array
        self.assertJSONSuccess(response, expected_keys=['banks'])
        
        data = response.json()
        self.assertEqual(data['banks'], [])


class VerifyAccountViewTestCase(BaseTestCase, PaystackMockMixin, AuthenticationMixin, JSONResponseMixin):
    """Test cases for verify_account API view"""
    
    def test_verify_account_unauthenticated(self):
        """Test API requires authentication"""
        self.assert_login_required(self.verify_account_url, method='POST')
    
    def test_verify_account_get_method(self):
        """Test GET method is not allowed"""
        response = self.authenticated_client.get(self.verify_account_url)
        
        self.assertJSONError(response, expected_error='Invalid request method')
    
    def test_verify_account_missing_parameters(self):
        """Test API with missing required parameters"""
        # Missing both parameters
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps({}),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Missing parameters')
        
        # Missing account_number
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps({'bank_code': '044'}),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Missing parameters')
        
        # Missing bank_code
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps({'account_number': '1234567890'}),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Missing parameters')
    
    @patch('payments.views.PaystackService')
    def test_verify_account_success(self, mock_paystack_service):
        """Test successful account verification"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = {
            'status': True,
            'data': {
                'account_name': 'John Doe',
                'account_number': '1234567890'
            }
        }
        
        data = {
            'account_number': '1234567890',
            'bank_code': '044'
        }
        
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertJSONSuccess(response, expected_keys=['success', 'account_name'])
        
        response_data = response.json()
        self.assertTrue(response_data['success'])
        self.assertEqual(response_data['account_name'], 'John Doe')
        
        # Verify service was called with correct parameters
        mock_service.resolve_account_number.assert_called_once_with('1234567890', '044')
    
    @patch('payments.views.PaystackService')
    def test_verify_account_failure(self, mock_paystack_service):
        """Test failed account verification"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = {
            'status': False,
            'message': 'Could not resolve account name'
        }
        
        data = {
            'account_number': '9999999999',
            'bank_code': '044'
        }
        
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Invalid account details')
        
        response_data = response.json()
        self.assertFalse(response_data['success'])
    
    @patch('payments.views.PaystackService')
    def test_verify_account_none_response(self, mock_paystack_service):
        """Test account verification when service returns None"""
        # Setup mock
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = None
        
        data = {
            'account_number': '1234567890',
            'bank_code': '044'
        }
        
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Invalid account details')
    
    @patch('payments.views.PaystackService')
    def test_verify_account_service_exception(self, mock_paystack_service):
        """Test account verification when service raises exception"""
        # Setup mock to raise exception
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.side_effect = Exception("Network timeout")
        
        data = {
            'account_number': '1234567890',
            'bank_code': '044'
        }
        
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Invalid account details')
    
    def test_verify_account_invalid_json(self):
        """Test API with invalid JSON data"""
        response = self.authenticated_client.post(
            self.verify_account_url,
            data='invalid json',
            content_type='application/json'
        )
        
        # Should return error (handled by JSON decode exception)
        self.assertEqual(response.status_code, 400)
    
    def test_verify_account_empty_values(self):
        """Test API with empty parameter values"""
        data = {
            'account_number': '',
            'bank_code': ''
        }
        
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Missing parameters')
    
    def test_verify_account_whitespace_values(self):
        """Test API with whitespace-only parameter values"""
        data = {
            'account_number': '   ',
            'bank_code': '\t\n'
        }
        
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Missing parameters')
    
    @patch('payments.views.PaystackService')
    def test_verify_account_malformed_response(self, mock_paystack_service):
        """Test account verification with malformed service response"""
        # Setup mock with malformed response
        mock_service = Mock()
        mock_paystack_service.return_value = mock_service
        mock_service.resolve_account_number.return_value = {
            'status': True,
            # Missing 'data' key
        }
        
        data = {
            'account_number': '1234567890',
            'bank_code': '044'
        }
        
        response = self.authenticated_client.post(
            self.verify_account_url,
            data=json.dumps(data),
            content_type='application/json'
        )
        
        self.assertJSONError(response, expected_error='Invalid account details')