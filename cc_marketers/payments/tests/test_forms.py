# payments/tests/test_forms.py
from decimal import Decimal
from django.test import TestCase

from payments.forms import FundingForm, WithdrawalForm


class FundingFormTestCase(TestCase):
    """Test cases for FundingForm"""
    
    def test_valid_funding_form(self):
        """Test funding form with valid data"""
        form_data = {
            'amount': '500.00',
            'description': 'Test wallet funding'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['amount'], Decimal('500.00'))
        self.assertEqual(form.cleaned_data['description'], 'Test wallet funding')
    
    def test_valid_funding_form_without_description(self):
        """Test funding form with valid amount but no description"""
        form_data = {
            'amount': '1000.50'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['amount'], Decimal('1000.50'))
        self.assertEqual(form.cleaned_data['description'], '')
    
    def test_funding_form_minimum_amount_valid(self):
        """Test funding form with minimum valid amount"""
        form_data = {
            'amount': '100.00'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertTrue(form.is_valid())
    
    def test_funding_form_maximum_amount_valid(self):
        """Test funding form with maximum valid amount"""
        form_data = {
            'amount': '1000000.00'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertTrue(form.is_valid())
    
    def test_funding_form_amount_below_minimum(self):
        """Test funding form with amount below minimum"""
        form_data = {
            'amount': '50.00'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
        self.assertIn('Minimum funding amount', str(form.errors['amount']))
    
    def test_funding_form_amount_above_maximum(self):
        """Test funding form with amount above maximum"""
        form_data = {
            'amount': '2000000.00'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
        self.assertIn('Maximum funding amount', str(form.errors['amount']))
    
    def test_funding_form_missing_amount(self):
        """Test funding form without amount"""
        form_data = {
            'description': 'Test description'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_funding_form_invalid_amount_format(self):
        """Test funding form with invalid amount format"""
        form_data = {
            'amount': 'invalid_amount'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_funding_form_negative_amount(self):
        """Test funding form with negative amount"""
        form_data = {
            'amount': '-100.00'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_funding_form_zero_amount(self):
        """Test funding form with zero amount"""
        form_data = {
            'amount': '0.00'
        }
        
        form = FundingForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_funding_form_decimal_precision(self):
        """Test funding form with different decimal precisions"""
        # Valid: 2 decimal places
        form_data = {'amount': '123.45'}
        form = FundingForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Valid: 1 decimal place
        form_data = {'amount': '123.4'}
        form = FundingForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Valid: no decimal places
        form_data = {'amount': '123'}
        form = FundingForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_funding_form_long_description(self):
        """Test funding form with very long description"""
        form_data = {
            'amount': '500.00',
            'description': 'x' * 1000  # Very long description
        }
        
        form = FundingForm(data=form_data)
        
        # Form should still be valid as description has no length validation in the form
        self.assertTrue(form.is_valid())


class WithdrawalFormTestCase(TestCase):
    """Test cases for WithdrawalForm"""
    
    def test_valid_withdrawal_form(self):
        """Test withdrawal form with valid data"""
        form_data = {
            'amount': '500.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['amount'], Decimal('500.00'))
        self.assertEqual(form.cleaned_data['bank_code'], '044')
        self.assertEqual(form.cleaned_data['account_number'], '1234567890')
    
    def test_withdrawal_form_minimum_amount_valid(self):
        """Test withdrawal form with minimum valid amount"""
        form_data = {
            'amount': '100.00',
            'bank_code': '011',
            'account_number': '0123456789'
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertTrue(form.is_valid())
    
    def test_withdrawal_form_amount_below_minimum(self):
        """Test withdrawal form with amount below minimum"""
        form_data = {
            'amount': '50.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
        self.assertIn('Minimum withdrawal amount', str(form.errors['amount']))
    
    def test_withdrawal_form_missing_required_fields(self):
        """Test withdrawal form with missing required fields"""
        # Missing amount
        form_data = {
            'bank_code': '044',
            'account_number': '1234567890'
        }
        form = WithdrawalForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
        
        # Missing bank_code
        form_data = {
            'amount': '200.00',
            'account_number': '1234567890'
        }
        form = WithdrawalForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('bank_code', form.errors)
        
        # Missing account_number
        form_data = {
            'amount': '200.00',
            'bank_code': '044'
        }
        form = WithdrawalForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('account_number', form.errors)
    
    def test_withdrawal_form_invalid_account_number_length(self):
        """Test withdrawal form with invalid account number length"""
        # Too short
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '123456789'  # 9 digits
        }
        form = WithdrawalForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('account_number', form.errors)
        self.assertIn('exactly 10 digits', str(form.errors['account_number']))
        
        # Too long
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '12345678901'  # 11 digits
        }
        form = WithdrawalForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('account_number', form.errors)
        self.assertIn('exactly 10 digits', str(form.errors['account_number']))
    
    def test_withdrawal_form_non_numeric_account_number(self):
        """Test withdrawal form with non-numeric account number"""
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '123456789a'  # Contains letter
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('account_number', form.errors)
        self.assertIn('contain only digits', str(form.errors['account_number']))
    
    def test_withdrawal_form_account_number_with_spaces(self):
        """Test withdrawal form with account number containing spaces"""
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '123 456 789'  # Contains spaces
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('account_number', form.errors)
    
    def test_withdrawal_form_account_number_with_special_chars(self):
        """Test withdrawal form with account number containing special characters"""
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '123-456-789'  # Contains hyphens
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('account_number', form.errors)
    
    def test_withdrawal_form_empty_bank_code(self):
        """Test withdrawal form with empty bank code"""
        form_data = {
            'amount': '200.00',
            'bank_code': '',
            'account_number': '1234567890'
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('bank_code', form.errors)
    
    def test_withdrawal_form_invalid_amount_format(self):
        """Test withdrawal form with invalid amount formats"""
        invalid_amounts = ['abc', '100.', '.50', '100..00', '100,00']
        
        for invalid_amount in invalid_amounts:
            with self.subTest(amount=invalid_amount):
                form_data = {
                    'amount': invalid_amount,
                    'bank_code': '044',
                    'account_number': '1234567890'
                }
                
                form = WithdrawalForm(data=form_data)
                
                self.assertFalse(form.is_valid())
                self.assertIn('amount', form.errors)
    
    def test_withdrawal_form_negative_amount(self):
        """Test withdrawal form with negative amount"""
        form_data = {
            'amount': '-100.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_withdrawal_form_zero_amount(self):
        """Test withdrawal form with zero amount"""
        form_data = {
            'amount': '0.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        
        form = WithdrawalForm(data=form_data)
        
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_withdrawal_form_bank_code_initialization(self):
        """Test that withdrawal form initializes bank_code choices correctly"""
        form = WithdrawalForm()
        
        # Check that bank_code field has initial empty choice
        bank_code_choices = form.fields['bank_code'].widget.choices
        self.assertEqual(bank_code_choices[0], ('', 'Select Bank'))
    
    def test_withdrawal_form_field_attributes(self):
        """Test that form fields have correct HTML attributes"""
        form = WithdrawalForm()
        
        # Check amount field attributes
        amount_widget = form.fields['amount'].widget
        self.assertIn('class', amount_widget.attrs)
        self.assertIn('placeholder', amount_widget.attrs)
        self.assertEqual(amount_widget.attrs['step'], '0.01')
        
        # Check account_number field attributes
        account_widget = form.fields['account_number'].widget
        self.assertIn('class', account_widget.attrs)
        self.assertIn('placeholder', account_widget.attrs)
        self.assertEqual(account_widget.attrs['id'], 'account_number')
        
        # Check bank_code field attributes
        bank_widget = form.fields['bank_code'].widget
        self.assertIn('class', bank_widget.attrs)
        self.assertEqual(bank_widget.attrs['id'], 'bank_select')
    
    def test_withdrawal_form_help_texts(self):
        """Test that form fields have appropriate help texts"""
        form = WithdrawalForm()
        
        self.assertEqual(form.fields['amount'].help_text, 'Minimum withdrawal amount is ₦100')
        self.assertEqual(form.fields['bank_code'].help_text, 'Select your bank')
        self.assertEqual(form.fields['account_number'].help_text, 'Your 10-digit account number')
    
    def test_withdrawal_form_clean_amount_edge_cases(self):
        """Test withdrawal form amount cleaning with edge cases"""
        # Test exactly at minimum
        form_data = {
            'amount': '100.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        form = WithdrawalForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['amount'], Decimal('100.00'))
        
        # Test just below minimum
        form_data = {
            'amount': '99.99',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        form = WithdrawalForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)
    
    def test_withdrawal_form_clean_account_number_edge_cases(self):
        """Test withdrawal form account number cleaning with edge cases"""
        # Test exactly 10 digits
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '1234567890'
        }
        form = WithdrawalForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['account_number'], '1234567890')
        
        # Test leading zeros
        form_data = {
            'amount': '200.00',
            'bank_code': '044',
            'account_number': '0123456789'
        }
        form = WithdrawalForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['account_number'], '0123456789')