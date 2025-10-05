# payments/tests/test_webhook_views.py
import json
import hmac
import hashlib
from unittest.mock import patch, Mock
from django.conf import settings
from django.test import override_settings

from payments.models import WebhookEvent
from .test_base import BaseTestCase


class PaystackWebhookViewTestCase(BaseTestCase):
    """Test cases for paystack_webhook view"""
    
    def setUp(self):
        super().setUp()
        self.webhook_payload = {
            'event': 'charge.success',
            'data': {
                'reference': 'TEST_REF_123',
                'amount': 50000,  # 500.00 in kobo
                'status': 'success',
                'gateway_response': 'Successful'
            }
        }
        self.webhook_json = json.dumps(self.webhook_payload).encode('utf-8')
    
    def generate_paystack_signature(self, payload):
        """Generate valid Paystack webhook signature"""
        secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', 'test_secret_key')
        return hmac.new(
            secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
    
    def test_webhook_missing_signature(self):
        """Test webhook with missing signature header"""
        response = self.client.post(
            self.webhook_url,
            data=self.webhook_json,
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), 'No signature')
    
    def test_webhook_invalid_signature(self):
        """Test webhook with invalid signature"""
        response = self.client.post(
            self.webhook_url,
            data=self.webhook_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE='invalid_signature'
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), 'Invalid signature')
    
    def test_webhook_invalid_json(self):
        """Test webhook with invalid JSON payload"""
        invalid_json = b'invalid json data'
        signature = self.generate_paystack_signature(invalid_json)
        
        response = self.client.post(
            self.webhook_url,
            data=invalid_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), 'Invalid JSON')
    
    @patch('payments.views.WebhookService.process_paystack_webhook')
    def test_webhook_successful_processing(self, mock_process_webhook):
        """Test webhook with successful event processing"""
        mock_process_webhook.return_value = {
            'success': True,
            'message': 'Event processed successfully'
        }
        
        signature = self.generate_paystack_signature(self.webhook_json)
        
        response = self.client.post(
            self.webhook_url,
            data=self.webhook_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'OK')
        
        # Verify webhook service was called
        mock_process_webhook.assert_called_once_with(self.webhook_payload)
    
    @patch('payments.views.WebhookService.process_paystack_webhook')
    def test_webhook_processing_failure(self, mock_process_webhook):
        """Test webhook with failed event processing"""
        error_message = 'Transaction not found'
        mock_process_webhook.return_value = {
            'success': False,
            'error': error_message
        }
        
        signature = self.generate_paystack_signature(self.webhook_json)
        
        response = self.client.post(
            self.webhook_url,
            data=self.webhook_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), error_message)
    
    @patch('payments.views.WebhookService.process_paystack_webhook')
    def test_webhook_processing_exception(self, mock_process_webhook):
        """Test webhook when processing raises an exception"""
        mock_process_webhook.side_effect = Exception('Database connection failed')
        
        signature = self.generate_paystack_signature(self.webhook_json)
        
        response = self.client.post(
            self.webhook_url,
            data=self.webhook_json,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, 500)
        self.assertIn('Internal error', response.content.decode())
    
    def test_webhook_get_method_not_allowed(self):
        """Test webhook endpoint doesn't accept GET requests"""
        response = self.client.get(self.webhook_url)
        
        self.assertEqual(response.status_code, 405)  # Method Not Allowed
    
    def test_webhook_put_method_not_allowed(self):
        """Test webhook endpoint doesn't accept PUT requests"""
        response = self.client.put(self.webhook_url)
        
        self.assertEqual(response.status_code, 405)  # Method Not Allowed
    
    @patch('payments.views.WebhookService.verify_paystack_signature')
    def test_webhook_signature_verification_called(self, mock_verify_signature):
        """Test that signature verification is properly called"""
        mock_verify_signature.return_value = True
        
        # Mock the webhook processing to avoid errors
        with patch('payments.views.WebhookService.process_paystack_webhook') as mock_process:
            mock_process.return_value = {'success': True}
            
            signature = 'test_signature'
            
            response = self.client.post(
                self.webhook_url,
                data=self.webhook_json,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature
            )
            
            # Verify signature verification was called with correct parameters
            mock_verify_signature.assert_called_once_with(self.webhook_json, signature)
    
    @override_settings(PAYSTACK_SECRET_KEY='test_webhook_key')
    def test_webhook_with_custom_secret_key(self):
        """Test webhook signature verification with custom secret key"""
        # Generate signature with custom key
        secret_key = 'test_webhook_key'
        signature = hmac.new(
            secret_key.encode('utf-8'),
            self.webhook_json,
            hashlib.sha512
        ).hexdigest()
        
        with patch('payments.views.WebhookService.process_paystack_webhook') as mock_process:
            mock_process.return_value = {'success': True}
            
            response = self.client.post(
                self.webhook_url,
                data=self.webhook_json,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature
            )
            
            self.assertEqual(response.status_code, 200)
    
    def test_webhook_empty_payload(self):
        """Test webhook with empty payload"""
        empty_payload = b''
        signature = self.generate_paystack_signature(empty_payload)
        
        response = self.client.post(
            self.webhook_url,
            data=empty_payload,
            content_type='application/json',
            HTTP_X_PAYSTACK_SIGNATURE=signature
        )
        
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), 'Invalid JSON')
    
    def test_webhook_large_payload(self):
        """Test webhook with large payload"""
        # Create a large payload
        large_payload = {
            'event': 'charge.success',
            'data': {
                'reference': 'TEST_REF_123',
                'amount': 50000,
                'large_data': 'x' * 10000  # 10KB of data
            }
        }
        large_json = json.dumps(large_payload).encode('utf-8')
        signature = self.generate_paystack_signature(large_json)
        
        with patch('payments.views.WebhookService.process_paystack_webhook') as mock_process:
            mock_process.return_value = {'success': True}
            
            response = self.client.post(
                self.webhook_url,
                data=large_json,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature
            )
            
            self.assertEqual(response.status_code, 200)
    
    def test_webhook_charge_success_event(self):
        """Test webhook specifically for charge.success event"""
        payload = {
            'event': 'charge.success',
            'data': {
                'reference': 'PS_TEST_123',
                'amount': 25000,
                'status': 'success'
            }
        }
        json_payload = json.dumps(payload).encode('utf-8')
        signature = self.generate_paystack_signature(json_payload)
        
        with patch('payments.views.WebhookService.process_paystack_webhook') as mock_process:
            mock_process.return_value = {'success': True}
            
            response = self.client.post(
                self.webhook_url,
                data=json_payload,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature
            )
            
            self.assertEqual(response.status_code, 200)
            mock_process.assert_called_once_with(payload)
    
    def test_webhook_transfer_success_event(self):
        """Test webhook specifically for transfer.success event"""
        payload = {
            'event': 'transfer.success',
            'data': {
                'reference': 'WD_TEST_123',
                'amount': 15000,
                'status': 'success',
                'transfer_code': 'TRF_123'
            }
        }
        json_payload = json.dumps(payload).encode('utf-8')
        signature = self.generate_paystack_signature(json_payload)
        
        with patch('payments.views.WebhookService.process_paystack_webhook') as mock_process:
            mock_process.return_value = {'success': True}
            
            response = self.client.post(
                self.webhook_url,
                data=json_payload,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature
            )
            
            self.assertEqual(response.status_code, 200)
            mock_process.assert_called_once_with(payload)
    
    def test_webhook_transfer_failed_event(self):
        """Test webhook specifically for transfer.failed event"""
        payload = {
            'event': 'transfer.failed',
            'data': {
                'reference': 'WD_TEST_123',
                'amount': 15000,
                'status': 'failed',
                'transfer_code': 'TRF_123'
            }
        }
        json_payload = json.dumps(payload).encode('utf-8')
        signature = self.generate_paystack_signature(json_payload)
        
        with patch('payments.views.WebhookService.process_paystack_webhook') as mock_process:
            mock_process.return_value = {'success': True}
            
            response = self.client.post(
                self.webhook_url,
                data=json_payload,
                content_type='application/json',
                HTTP_X_PAYSTACK_SIGNATURE=signature
            )
            
            self.assertEqual(response.status_code, 200)
            mock_process.assert_called_once_with(payload)