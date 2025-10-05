# payments/tests/test_models.py
import uuid
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from payments.models import (
    PaymentGateway, PaymentTransaction, PaystackTransaction, WebhookEvent
)
from .test_base import BaseTestCase


class PaymentGatewayModelTestCase(BaseTestCase):
    """Test cases for PaymentGateway model"""
    
    def test_create_payment_gateway(self):
        """Test creating a payment gateway"""
        gateway = PaymentGateway.objects.create(
            name='stripe',
            is_active=True,
            config={'api_key': 'test_key', 'webhook_secret': 'test_secret'}
        )
        
        self.assertEqual(gateway.name, 'stripe')
        self.assertTrue(gateway.is_active)
        self.assertEqual(gateway.config['api_key'], 'test_key')
        self.assertIsNotNone(gateway.created_at)
    
    def test_payment_gateway_str_method(self):
        """Test PaymentGateway string representation"""
        gateway = PaymentGateway.objects.create(name='test_gateway')
        
        self.assertEqual(str(gateway), 'test_gateway')
    
    def test_payment_gateway_unique_name(self):
        """Test that gateway names must be unique"""
        PaymentGateway.objects.create(name='duplicate_name')
        
        with self.assertRaises(IntegrityError):
            PaymentGateway.objects.create(name='duplicate_name')
    
    def test_payment_gateway_default_values(self):
        """Test PaymentGateway default field values"""
        gateway = PaymentGateway.objects.create(name='test_defaults')
        
        self.assertTrue(gateway.is_active)  # Default should be True
        self.assertEqual(gateway.config, {})  # Default should be empty dict
        self.assertIsNotNone(gateway.created_at)
    
    def test_payment_gateway_meta_options(self):
        """Test PaymentGateway meta options"""
        self.assertEqual(PaymentGateway._meta.db_table, 'payment_gateways')


class PaymentTransactionModelTestCase(BaseTestCase):
    """Test cases for PaymentTransaction model"""
    
    def test_create_payment_transaction(self):
        """Test creating a payment transaction"""
        transaction = PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            amount=Decimal('250.50'),
            currency='USD',
            gateway_reference='TEST_REF_001',
            status=PaymentTransaction.Status.PENDING
        )
        
        self.assertEqual(transaction.user, self.user)
        self.assertEqual(transaction.gateway, self.gateway)
        self.assertEqual(transaction.transaction_type, 'funding')
        self.assertEqual(transaction.amount, Decimal('250.50'))
        self.assertEqual(transaction.currency, 'USD')
        self.assertEqual(transaction.gateway_reference, 'TEST_REF_001')
        self.assertEqual(transaction.status, 'pending')
    
    def test_payment_transaction_auto_fields(self):
        """Test PaymentTransaction auto-generated fields"""
        transaction = PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
            amount=Decimal('100.00'),
            gateway_reference='AUTO_REF_001'
        )
        
        # Check UUID primary key
        self.assertIsInstance(transaction.id, uuid.UUID)
        
        # Check auto-generated internal reference
        self.assertTrue(transaction.internal_reference.startswith('TXN_'))
        
        # Check timestamps
        self.assertIsNotNone(transaction.created_at)
        self.assertIsNotNone(transaction.updated_at)
        self.assertIsNone(transaction.completed_at)  # Should be None initially
    
    def test_payment_transaction_default_values(self):
        """Test PaymentTransaction default field values"""
        transaction = PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            amount=Decimal('100.00'),
            gateway_reference='DEFAULT_REF_001'
        )
        
        self.assertEqual(transaction.currency, 'NGN')  # Default currency
        self.assertEqual(transaction.status, 'pending')  # Default status
        self.assertEqual(transaction.gateway_response, {})  # Default empty dict
        self.assertEqual(transaction.metadata, {})  # Default empty dict
    
    def test_payment_transaction_str_method(self):
        """Test PaymentTransaction string representation"""
        transaction = PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            amount=Decimal('150.75'),
            currency='USD',
            gateway_reference='STR_TEST_REF'
        )
        
        expected_str = f"Funding - {self.user} - 150.75 USD"
        self.assertEqual(str(transaction), expected_str)
    
    def test_payment_transaction_unique_gateway_reference(self):
        """Test that gateway_reference must be unique"""
        PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            amount=Decimal('100.00'),
            gateway_reference='UNIQUE_REF'
        )
        
        with self.assertRaises(IntegrityError):
            PaymentTransaction.objects.create(
                user=self.other_user,
                gateway=self.gateway,
                transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
                amount=Decimal('200.00'),
                gateway_reference='UNIQUE_REF'  # Duplicate reference
            )
    
    def test_payment_transaction_unique_internal_reference(self):
        """Test that internal_reference must be unique"""
        transaction1 = PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            amount=Decimal('100.00'),
            gateway_reference='REF_001'
        )
        
        # Try to create another transaction with the same internal reference
        with self.assertRaises(IntegrityError):
            PaymentTransaction.objects.create(
                user=self.other_user,
                gateway=self.gateway,
                transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
                amount=Decimal('200.00'),
                gateway_reference='REF_002',
                internal_reference=transaction1.internal_reference
            )
    
    def test_payment_transaction_choices(self):
        """Test PaymentTransaction choice fields"""
        # Test TransactionType choices
        self.assertEqual(PaymentTransaction.TransactionType.FUNDING, 'funding')
        self.assertEqual(PaymentTransaction.TransactionType.WITHDRAWAL, 'withdrawal')
        
        # Test Status choices
        self.assertEqual(PaymentTransaction.Status.PENDING, 'pending')
        self.assertEqual(PaymentTransaction.Status.SUCCESS, 'success')
        self.assertEqual(PaymentTransaction.Status.FAILED, 'failed')
        self.assertEqual(PaymentTransaction.Status.CANCELLED, 'cancelled')
    
    def test_payment_transaction_ordering(self):
        """Test PaymentTransaction default ordering"""
        # Create transactions at different times
        transaction1 = PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            amount=Decimal('100.00'),
            gateway_reference='ORDER_REF_001'
        )
        
        transaction2 = PaymentTransaction.objects.create(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
            amount=Decimal('200.00'),
            gateway_reference='ORDER_REF_002'
        )
        
        # Get all transactions - should be ordered by created_at descending
        transactions = list(PaymentTransaction.objects.all())
        
        # Most recent should be first
        self.assertEqual(transactions[0].id, transaction2.id)
        self.assertEqual(transactions[1].id, transaction1.id)
    
    def test_payment_transaction_meta_options(self):
        """Test PaymentTransaction meta options"""
        self.assertEqual(PaymentTransaction._meta.db_table, 'payment_transactions')
        self.assertEqual(PaymentTransaction._meta.ordering, ['-created_at'])
    
    def test_payment_transaction_save_method(self):
        """Test PaymentTransaction save method generates internal reference"""
        transaction = PaymentTransaction(
            user=self.user,
            gateway=self.gateway,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            amount=Decimal('100.00'),
            gateway_reference='SAVE_METHOD_REF'
        )
        
        # Before saving, internal_reference should be empty
        self.assertFalse(transaction.internal_reference)
        
        transaction.save()
        
        # After saving, internal_reference should be generated
        self.assertTrue(transaction.internal_reference.startswith('TXN_'))
        self.assertIn(str(transaction.id)[:8], transaction.internal_reference)


class PaystackTransactionModelTestCase(BaseTestCase):
    """Test cases for PaystackTransaction model"""
    
    def setUp(self):
        super().setUp()
        self.payment_transaction = self.create_payment_transaction()
    
    def test_create_paystack_transaction(self):
        """Test creating a Paystack transaction"""
        paystack_transaction = PaystackTransaction.objects.create(
            transaction=self.payment_transaction,
            authorization_url='https://checkout.paystack.com/test123',
            access_code='test_access_code',
            paystack_reference='PS_TEST_REF_001',
            recipient_code='RCP_test123',
            transfer_code='TRF_test456',
            bank_code='044',
            account_number='1234567890',
            account_name='Test User'
        )
        
        self.assertEqual(paystack_transaction.transaction, self.payment_transaction)
        self.assertEqual(paystack_transaction.authorization_url, 'https://checkout.paystack.com/test123')
        self.assertEqual(paystack_transaction.access_code, 'test_access_code')
        self.assertEqual(paystack_transaction.paystack_reference, 'PS_TEST_REF_001')
        self.assertEqual(paystack_transaction.recipient_code, 'RCP_test123')
        self.assertEqual(paystack_transaction.transfer_code, 'TRF_test456')
        self.assertEqual(paystack_transaction.bank_code, '044')
        self.assertEqual(paystack_transaction.account_number, '1234567890')
        self.assertEqual(paystack_transaction.account_name, 'Test User')
    
    def test_paystack_transaction_str_method(self):
        """Test PaystackTransaction string representation"""
        paystack_transaction = PaystackTransaction.objects.create(
            transaction=self.payment_transaction,
            paystack_reference='PS_STR_TEST_REF'
        )
        
        expected_str = "Paystack - PS_STR_TEST_REF"
        self.assertEqual(str(paystack_transaction), expected_str)
    
    def test_paystack_transaction_one_to_one_relationship(self):
        """Test one-to-one relationship with PaymentTransaction"""
        paystack_transaction = PaystackTransaction.objects.create(
            transaction=self.payment_transaction,
            paystack_reference='PS_RELATION_TEST'
        )
        
        # Test forward relationship
        self.assertEqual(paystack_transaction.transaction, self.payment_transaction)
        
        # Test reverse relationship
        self.assertEqual(self.payment_transaction.paystack_details, paystack_transaction)
    
    def test_paystack_transaction_unique_paystack_reference(self):
        """Test that paystack_reference must be unique"""
        PaystackTransaction.objects.create(
            transaction=self.payment_transaction,
            paystack_reference='UNIQUE_PS_REF'
        )
        
        # Create another payment transaction
        other_payment_transaction = self.create_payment_transaction(
            user=self.other_user,
            gateway_reference='OTHER_REF'
        )
        
        with self.assertRaises(IntegrityError):
            PaystackTransaction.objects.create(
                transaction=other_payment_transaction,
                paystack_reference='UNIQUE_PS_REF'  # Duplicate reference
            )
    
    def test_paystack_transaction_optional_fields(self):
        """Test PaystackTransaction with only required fields"""
        paystack_transaction = PaystackTransaction.objects.create(
            transaction=self.payment_transaction,
            paystack_reference='PS_MINIMAL_REF'
        )
        
        # Check that optional fields are empty/blank
        self.assertEqual(paystack_transaction.authorization_url, '')
        self.assertEqual(paystack_transaction.access_code, '')
        self.assertEqual(paystack_transaction.recipient_code, '')
        self.assertEqual(paystack_transaction.transfer_code, '')
        self.assertEqual(paystack_transaction.bank_code, '')
        self.assertEqual(paystack_transaction.account_number, '')
        self.assertEqual(paystack_transaction.account_name, '')
    
    def test_paystack_transaction_meta_options(self):
        """Test PaystackTransaction meta options"""
        self.assertEqual(PaystackTransaction._meta.db_table, 'paystack_transactions')
    
    def test_paystack_transaction_cascade_delete(self):
        """Test that PaystackTransaction is deleted when PaymentTransaction is deleted"""
        paystack_transaction = PaystackTransaction.objects.create(
            transaction=self.payment_transaction,
            paystack_reference='PS_CASCADE_TEST'
        )
        
        paystack_id = paystack_transaction.id
        
        # Delete the payment transaction
        self.payment_transaction.delete()
        
        # PaystackTransaction should also be deleted
        self.assertFalse(PaystackTransaction.objects.filter(id=paystack_id).exists())


class WebhookEventModelTestCase(BaseTestCase):
    """Test cases for WebhookEvent model"""
    
    def test_create_webhook_event(self):
        """Test creating a webhook event"""
        webhook_event = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.CHARGE_SUCCESS,
            reference='WEBHOOK_TEST_REF',
            payload={'event': 'charge.success', 'data': {'reference': 'test'}},
            processed=False
        )
        
        self.assertEqual(webhook_event.gateway, self.gateway)
        self.assertEqual(webhook_event.event_type, 'charge.success')
        self.assertEqual(webhook_event.reference, 'WEBHOOK_TEST_REF')
        self.assertEqual(webhook_event.payload['event'], 'charge.success')
        self.assertFalse(webhook_event.processed)
        self.assertIsNone(webhook_event.processed_at)
    
    def test_webhook_event_str_method(self):
        """Test WebhookEvent string representation"""
        webhook_event = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.TRANSFER_SUCCESS,
            reference='WEBHOOK_STR_TEST',
            payload={}
        )
        
        expected_str = f"{self.gateway.name} - transfer.success - WEBHOOK_STR_TEST"
        self.assertEqual(str(webhook_event), expected_str)
    
    def test_webhook_event_default_values(self):
        """Test WebhookEvent default field values"""
        webhook_event = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.OTHER,
            reference='DEFAULT_TEST_REF',
            payload={}
        )
        
        self.assertFalse(webhook_event.processed)  # Default should be False
        self.assertIsNone(webhook_event.processed_at)  # Default should be None
        self.assertIsNotNone(webhook_event.created_at)
    
    def test_webhook_event_choices(self):
        """Test WebhookEvent event type choices"""
        self.assertEqual(WebhookEvent.EventType.CHARGE_SUCCESS, 'charge.success')
        self.assertEqual(WebhookEvent.EventType.TRANSFER_SUCCESS, 'transfer.success')
        self.assertEqual(WebhookEvent.EventType.TRANSFER_FAILED, 'transfer.failed')
        self.assertEqual(WebhookEvent.EventType.OTHER, 'other')
    
    def test_webhook_event_processed_timestamp(self):
        """Test webhook event processed timestamp handling"""
        webhook_event = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.CHARGE_SUCCESS,
            reference='PROCESSED_TEST_REF',
            payload={}
        )
        
        # Initially not processed
        self.assertFalse(webhook_event.processed)
        self.assertIsNone(webhook_event.processed_at)
        
        # Mark as processed
        webhook_event.processed = True
        webhook_event.processed_at = timezone.now()
        webhook_event.save()
        
        self.assertTrue(webhook_event.processed)
        self.assertIsNotNone(webhook_event.processed_at)
    
    def test_webhook_event_reference_indexing(self):
        """Test that reference field has database index"""
        # This is more of a structural test - checking meta options
        reference_field = WebhookEvent._meta.get_field('reference')
        self.assertTrue(reference_field.db_index)
    
    def test_webhook_event_ordering(self):
        """Test WebhookEvent default ordering"""
        # Create multiple webhook events
        webhook1 = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.CHARGE_SUCCESS,
            reference='ORDER_TEST_REF_001',
            payload={}
        )
        
        webhook2 = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.TRANSFER_SUCCESS,
            reference='ORDER_TEST_REF_002',
            payload={}
        )
        
        # Get all webhook events - should be ordered by created_at descending
        webhooks = list(WebhookEvent.objects.all())
        
        # Most recent should be first
        self.assertEqual(webhooks[0].id, webhook2.id)
        self.assertEqual(webhooks[1].id, webhook1.id)
    
    def test_webhook_event_meta_options(self):
        """Test WebhookEvent meta options"""
        self.assertEqual(WebhookEvent._meta.db_table, 'webhook_events')
        self.assertEqual(WebhookEvent._meta.ordering, ['-created_at'])
    
    def test_webhook_event_cascade_delete(self):
        """Test that WebhookEvent is deleted when PaymentGateway is deleted"""
        webhook_event = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.CHARGE_SUCCESS,
            reference='CASCADE_DELETE_TEST',
            payload={}
        )
        
        webhook_id = webhook_event.id
        
        # Delete the gateway
        self.gateway.delete()
        
        # WebhookEvent should also be deleted
        self.assertFalse(WebhookEvent.objects.filter(id=webhook_id).exists())
    
    def test_webhook_event_large_payload(self):
        """Test WebhookEvent with large JSON payload"""
        large_payload = {
            'event': 'charge.success',
            'data': {
                'reference': 'LARGE_PAYLOAD_TEST',
                'metadata': {
                    'large_field': 'x' * 5000  # 5KB of data
                },
                'customer': {
                    'email': 'test@example.com',
                    'name': 'Test Customer'
                }
            }
        }
        
        webhook_event = WebhookEvent.objects.create(
            gateway=self.gateway,
            event_type=WebhookEvent.EventType.CHARGE_SUCCESS,
            reference='LARGE_PAYLOAD_REF',
            payload=large_payload
        )
        
        # Should save and retrieve successfully
        self.assertEqual(webhook_event.payload['event'], 'charge.success')
        self.assertEqual(len(webhook_event.payload['data']['metadata']['large_field']), 5000)