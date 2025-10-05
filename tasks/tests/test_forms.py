# tests/test_forms.py
"""
Test suite for all task-related forms.
Tests form validation, widget rendering, and edge cases.
"""
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from tasks.forms import (
    TaskForm
)
from .test_base import ComprehensiveTaskTestCase


class TaskFormTest(ComprehensiveTaskTestCase):
    """Test cases for TaskForm."""

    def test_valid_task_form(self):
        """Test form with valid data."""
        future_date = timezone.now() + timedelta(days=7)
        data = {
            'title': 'Test Task',
            'description': 'This is a test task',
            'payout_per_slot': '15.50',
            'total_slots': '5',
            'deadline': future_date.strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Please provide screenshot and description'
        }
        
        form = TaskForm(data=data)
        self.assertTrue(form.is_valid())
        
        # Test form saves correctly
        task = form.save(commit=False)
        task.advertiser = self.advertiser
        task.save()
        
        self.assertEqual(task.title, 'Test Task')
        self.assertEqual(task.payout_per_slot, Decimal('15.50'))
        self.assertEqual(task.total_slots, 5)

    def test_required_fields(self):
        """Test that required fields are enforced."""
        form = TaskForm(data={})
        self.assertFalse(form.is_valid())
        
        required_fields = ['title', 'description', 'payout_per_slot', 'total_slots', 'deadline', 'proof_instructions']
        for field in required_fields:
            self.assertIn(field, form.errors)

    def test_minimum_payout_validation(self):
        """Test minimum payout validation."""
        future_date = timezone.now() + timedelta(days=7)
        data = {
            'title': 'Test Task',
            'description': 'Description',
            'payout_per_slot': '0.00',  # Below minimum
            'total_slots': '1',
            'deadline': future_date.strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Instructions'
        }
        
        form = TaskForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('payout_per_slot', form.errors)

    def test_minimum_slots_validation(self):
        """Test minimum slots validation."""
        future_date = timezone.now() + timedelta(days=7)
        data = {
            'title': 'Test Task',
            'description': 'Description',
            'payout_per_slot': '10.00',
            'total_slots': '0',  # Below minimum
            'deadline': future_date.strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Instructions'
        }
        
        form = TaskForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('total_slots', form.errors)

    def test_deadline_widget_type(self):
        """Test that deadline widget has correct type."""
        form = TaskForm()
        deadline_widget = form.fields['deadline'].widget
        self.assertEqual(deadline_widget.input_type, 'datetime-local')

    def test_payout_widget_attributes(self):
        """Test payout field widget attributes."""
        form = TaskForm()
        payout_widget = form.fields['payout_per_slot'].widget
        self.assertEqual(payout_widget.attrs.get('step'), '0.01')
        self.assertEqual(payout_widget.attrs.get('min'), '0.01')

    def test_slots_widget_attributes(self):
        """Test total slots widget attributes."""
        form = TaskForm()
        slots_widget = form.fields['total_slots'].widget
        self.assertEqual(slots_widget.attrs.get('min'), '1')

    def test_textarea_widgets_rows(self):
        """Test textarea widgets have correct rows."""
        form = TaskForm()
        self.assertEqual(form.fields['description'].widget.attrs.get('rows'), 4)
        self.assertEqual(form.fields['proof_instructions'].widget.attrs.get('rows'), 3)

    def test_form_with_existing_instance(self):
        """Test form initialization with existing task instance."""
        task = self.create_task(
            title='Existing Task',
            payout_per_slot=Decimal('20.00'),
            total_slots=3
        )
        
        form = TaskForm(instance=task)
        
        self.assertEqual(form.initial['title'], 'Existing Task')
        self.assertEqual(form.initial['payout_per_slot'], Decimal('20.00'))
        self.assertEqual(form.initial['total_slots'], 3)

    def test_form_save_with_commit_false(self):
        """Test form save with commit=False."""
        future_date = timezone.now() + timedelta(days=7)
        {
            'title': 'Test Task',
            'description': 'Description',
            'payout_per_slot': '25.00',
            'total_slots': '2',
            'deadline': future_date.strftime('%Y-%m-%dT%H:%M'),
            'proof_instructions': 'Instructions'
        }