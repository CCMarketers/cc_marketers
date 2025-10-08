# tests/test_signals.py
from django.test import TestCase
from django.db.models.signals import post_save
from unittest.mock import patch
from io import StringIO
import sys

from subscriptions.models import UserSubscription
from subscriptions.signals import subscription_activated
from .test_base import BaseTestMixin
from subscriptions import signals


class SubscriptionSignalsTest(BaseTestMixin, TestCase):
    """Test subscription signals"""

    def test_subscription_activated_signal_connected(self):
        """Test that subscription_activated signal is properly connected"""
        connected_receivers = [
            r[1]() for r in post_save.receivers if r[1]()
        ]
        handler_names = [
            getattr(receiver, "__name__", repr(receiver))
            for receiver in connected_receivers
        ]
        self.assertIn('subscription_activated', handler_names)



    def test_subscription_activated_signal_triggered_on_creation(self):
        """Test signal is triggered when new active subscription is created"""
        # Capture stdout to verify print statement
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Create new active subscription
            self.create_subscription()
            
            # Get the printed output
            output = captured_output.getvalue()
            
            # Verify the signal was triggered
            self.assertIn("New subscription activated", output)
            self.assertIn(self.user.username, output)
            self.assertIn(self.basic_plan.name, output)
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_not_triggered_on_update(self):
        """Test signal is not triggered when subscription is updated"""
        # Create subscription first
        subscription = self.create_subscription()
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Update existing subscription
            subscription.auto_renewal = False
            subscription.save()
            
            # Get the printed output
            output = captured_output.getvalue()
            
            # Signal should not be triggered for updates
            self.assertEqual(output.strip(), "")
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_inactive_subscription(self):
        """Test signal behavior with inactive subscription creation"""
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Create cancelled subscription
            self.create_subscription(status='cancelled')
            
            # Get the printed output
            output = captured_output.getvalue()
            
            # Signal should not print for non-active subscriptions
            self.assertEqual(output.strip(), "")
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_expired_subscription(self):
        """Test signal behavior with expired subscription creation"""
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Create expired subscription
            self.create_subscription(status='expired')
            
            # Get the printed output
            output = captured_output.getvalue()
            
            # Signal should not print for expired subscriptions
            self.assertEqual(output.strip(), "")
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_with_different_plans(self):
        """Test signal with different subscription plans"""
        plans_to_test = [
            (self.basic_plan, 'Basic Plan'),
            (self.business_plan, 'Business Member Account'),
            (self.premium_plan, 'Premium Plan')
        ]
        
        for plan, plan_name in plans_to_test:
            with self.subTest(plan=plan_name):
                # Capture stdout
                old_stdout = sys.stdout
                captured_output = StringIO()
                sys.stdout = captured_output
                
                try:
                    # Create subscription with specific plan
                    self.create_subscription(
                        user=self.user2,  # Use different user each time
                        plan=plan
                    )
                    
                    # Get the printed output
                    output = captured_output.getvalue()
                    
                    # Verify correct plan name in output
                    self.assertIn("New subscription activated", output)
                    self.assertIn(plan_name, output)
                    
                finally:
                    sys.stdout = old_stdout

    def test_subscription_activated_signal_with_different_users(self):
        """Test signal with different users"""
        users_to_test = [
            (self.user, 'testuser'),
            (self.user2, 'testuser2'),
            (self.admin_user, 'admin')
        ]
        
        for user, username in users_to_test:
            with self.subTest(user=username):
                # Capture stdout
                old_stdout = sys.stdout
                captured_output = StringIO()
                sys.stdout = captured_output
                
                try:
                    # Create subscription for specific user
                    self.create_subscription(user=user)
                    
                    # Get the printed output
                    output = captured_output.getvalue()
                    
                    # Verify correct username in output
                    self.assertIn("New subscription activated", output)
                    self.assertIn(username, output)
                    
                finally:
                    sys.stdout = old_stdout



        @patch('subscriptions.signals.print')
        def test_subscription_activated_signal_mocked(self, mock_print):
            # Ensure no duplicate connections
            post_save.disconnect(signals.subscription_activated, sender=UserSubscription)
            post_save.connect(signals.subscription_activated, sender=UserSubscription)

            # Act
            self.create_subscription()

            # Assert
            expected_message = f"New subscription activated for {self.user.username}: {self.basic_plan.name}"
            mock_print.assert_called_once_with(expected_message)

            # Cleanup: reconnect original to avoid side effects
            post_save.disconnect(signals.subscription_activated, sender=UserSubscription)
            post_save.connect(signals.subscription_activated, sender=UserSubscription)



    @patch('subscriptions.signals.print')
    def test_subscription_activated_signal_not_called_for_updates(self, mock_print):
        """Test signal not called for subscription updates using mock"""
        # Create subscription first
        subscription = self.create_subscription()
        
        # Reset mock to clear creation call
        mock_print.reset_mock()
        
        # Update subscription
        subscription.auto_renewal = False
        subscription.save()
        
        # Print should not be called for updates
        mock_print.assert_not_called()

    @patch('subscriptions.signals.print')
    def test_subscription_activated_signal_not_called_for_inactive(self, mock_print):
        """Test signal not called for inactive subscriptions using mock"""
        # Create cancelled subscription
        self.create_subscription(status='cancelled')
        
        # Print should not be called for inactive subscriptions
        mock_print.assert_not_called()

    def test_subscription_activated_signal_handler_parameters(self):
        """Test signal handler receives correct parameters"""
        from django.db.models.signals import post_save
        from subscriptions import signals

        # Disconnect real handler
        post_save.disconnect(signals.subscription_activated, sender=UserSubscription)

        with patch('subscriptions.signals.subscription_activated') as mock_handler:
            # Reconnect patched handler
            post_save.connect(mock_handler, sender=UserSubscription)

            subscription = self.create_subscription()

            mock_handler.assert_called_once()
            call_args = mock_handler.call_args
            self.assertEqual(call_args[1]['sender'], UserSubscription)
            self.assertEqual(call_args[1]['instance'], subscription)
            self.assertTrue(call_args[1]['created'])

        # Reconnect original handler
        post_save.connect(signals.subscription_activated, sender=UserSubscription)


    def test_subscription_activated_signal_direct_call(self):
        """Test calling signal handler directly"""
        subscription = self.create_subscription()
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Call signal handler directly
            subscription_activated(
                sender=UserSubscription,
                instance=subscription,
                created=True
            )
            
            # Get the printed output
            output = captured_output.getvalue()
            
            # Verify output
            self.assertIn("New subscription activated", output)
            self.assertIn(self.user.username, output)
            self.assertIn(self.basic_plan.name, output)
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_direct_call_not_created(self):
        """Test signal handler when created=False"""
        subscription = self.create_subscription()
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Call signal handler with created=False
            subscription_activated(
                sender=UserSubscription,
                instance=subscription,
                created=False
            )
            
            # Get the printed output
            output = captured_output.getvalue()
            
            # Should not print anything when not created
            self.assertEqual(output.strip(), "")
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_direct_call_inactive_status(self):
        """Test signal handler with inactive subscription status"""
        subscription = self.create_subscription(status='expired')
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Call signal handler directly
            subscription_activated(
                sender=UserSubscription,
                instance=subscription,
                created=True
            )
            
            # Get the printed output
            output = captured_output.getvalue()
            
            # Should not print for inactive subscriptions
            self.assertEqual(output.strip(), "")
            
        finally:
            sys.stdout = old_stdout

        from django.db.models.signals import post_save
        from subscriptions import signals

        def test_subscription_activated_signal_multiple_subscriptions(self):
            post_save.disconnect(signals.subscription_activated, sender=UserSubscription)
            post_save.connect(signals.subscription_activated, sender=UserSubscription)

            old_stdout = sys.stdout
            captured_output = StringIO()
            sys.stdout = captured_output

            try:
                self.create_subscription(user=self.user)
                self.create_subscription(user=self.user2, plan=self.premium_plan)
                output = captured_output.getvalue()
                activation_count = output.count("New subscription activated")
                self.assertEqual(activation_count, 2)
            finally:
                sys.stdout = old_stdout



    def test_subscription_activated_signal_exception_handling(self):
        """Test signal handler doesn't break on exceptions"""
        # Mock print to raise exception
        with patch('subscriptions.signals.print', side_effect=Exception("Print error")):
            # This should not raise an exception
            try:
                self.create_subscription()
                # If we get here, the signal didn't break the subscription creation
                self.assertTrue(True)
            except Exception as e:
                self.fail(f"Signal handler exception broke subscription creation: {e}")

    def test_subscription_activated_signal_user_display_methods(self):
        """Test signal works with different user display methods"""
        # Test with user that has username
        subscription = self.create_subscription()
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Trigger signal by calling directly
            subscription_activated(
                sender=UserSubscription,
                instance=subscription,
                created=True
            )
            
            output = captured_output.getvalue()
            self.assertIn(self.user.username, output)
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_plan_string_representation(self):
        """Test signal uses plan's string representation correctly"""
        # Create plans with different names
        special_plan = self.create_subscription_plan(
            name='Special-Plan_2023',
            price=self.basic_plan.price
        )
        
        subscription = self.create_subscription(plan=special_plan)
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Trigger signal
            subscription_activated(
                sender=UserSubscription,
                instance=subscription,
                created=True
            )
            
            output = captured_output.getvalue()
            self.assertIn('Special-Plan_2023', output)
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_kwargs_handling(self):
        """Test signal handler handles additional kwargs gracefully"""
        subscription = self.create_subscription()
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Call with additional kwargs
            subscription_activated(
                sender=UserSubscription,
                instance=subscription,
                created=True,
                extra_param="should_be_ignored",
                another_param=123
            )
            
            output = captured_output.getvalue()
            self.assertIn("New subscription activated", output)
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_integration(self):
        """Test signal integration with actual subscription creation process"""
        # This tests that signals work with the full subscription creation flow
        
        # Capture stdout
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            # Use the service to create subscription (more realistic)
            from subscriptions.services import SubscriptionService
            
            result = SubscriptionService.subscribe_user(self.user, self.basic_plan.id)
            self.assertTrue(result['success'])
            
            output = captured_output.getvalue()
            self.assertIn("New subscription activated", output)
            
        finally:
            sys.stdout = old_stdout

    def test_subscription_activated_signal_performance(self):
        """Test signal handler performance"""
        import time
        
        # Create subscription and measure time
        start_time = time.time()
        self.create_subscription()
        end_time = time.time()
        
        # Signal processing should be very fast (under 100ms)
        execution_time = end_time - start_time
        self.assertLess(execution_time, 0.1)

    # def test_subscription_activated_future_extensibility(self):
    #     """Test signal can be extended for future functionality"""
    #     # Mock additional functionality that could be added to the signal
    #     with patch('subscriptions.signals.subscription_activated', wraps=subscription_activated) as mock_signal:
    #         subscription = self.create_subscription()
            
    #         # Verify signal was called (extensibility point)
    #         mock_signal.assert_called()
            
    #         # Future functionality could be added here:
    #         # - Send welcome email
    #         # - Update user statistics
    #         # - Log analytics events
    #         # - Trigger integrations
            
    #         # For now, just verify the basic functionality works
    #         call_kwargs = mock_signal.call_args[1]
    #         self.assertEqual(call_kwargs['instance'], subscription)
    #         self.assertTrue(call_kwargs['created'])

    def test_subscription_activated_future_extensibility(self):
        """Test signal can be extended for future functionality"""

        # Disconnect real handler
        post_save.disconnect(signals.subscription_activated, sender=UserSubscription)

        with patch('subscriptions.signals.subscription_activated', wraps=signals.subscription_activated) as mock_signal:
            # Reconnect mocked handler
            post_save.connect(mock_signal, sender=UserSubscription)

            subscription = self.create_subscription()
            mock_signal.assert_called()

            call_kwargs = mock_signal.call_args[1]
            self.assertEqual(call_kwargs['instance'], subscription)
            self.assertTrue(call_kwargs['created'])

        # Reconnect original handler
        post_save.connect(signals.subscription_activated, sender=UserSubscription)
