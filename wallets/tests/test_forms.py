# wallets/tests/test_forms.py
from decimal import Decimal

from ..forms import WithdrawalRequestForm, FundWalletForm
from .test_base import BaseWalletTestCase
from wallets.tests.test_base import WalletTestCase

class WithdrawalRequestFormTest(WalletTestCase):
    """Test WithdrawalRequestForm functionality"""
    
    def setUp(self):
        super().setUp()
        self.valid_data = {
            'amount': Decimal('100.00'),
            'withdrawal_method': 'paystack',
            'account_number': '1234567890',
            'account_name': 'Test Account Name',
            'bank_name': 'Test Bank',
            'bank_code': '001'
        }
    
    def test_valid_form_data(self):
        """Test form with valid data"""
        form = self.assert_form_valid(WithdrawalRequestForm, self.valid_data)
        
        # Check cleaned data
        self.assertEqual(form.cleaned_data['amount'], Decimal('100.00'))
        self.assertEqual(form.cleaned_data['withdrawal_method'], 'paystack')
        self.assertEqual(form.cleaned_data['account_number'], '1234567890')
        self.assertEqual(form.cleaned_data['account_name'], 'Test Account Name')
        self.assertEqual(form.cleaned_data['bank_name'], 'Test Bank')
        self.assertEqual(form.cleaned_data['bank_code'], '001')
    
    def test_minimum_amount_validation(self):
        """Test minimum amount validation"""
        # Test amount below minimum
        invalid_data = self.valid_data.copy()
        invalid_data['amount'] = Decimal('0.50')
        
        self.assert_form_invalid(
            WithdrawalRequestForm, 
            invalid_data,
            {'amount': 'Minimum withdrawal amount is $1.00'}
        )
    
    def test_maximum_amount_validation(self):
        """Test maximum amount validation"""
        # Test amount above maximum
        invalid_data = self.valid_data.copy()
        invalid_data['amount'] = Decimal('10001.00')
        
        self.assert_form_invalid(
            WithdrawalRequestForm,
            invalid_data,
            {'amount': 'Maximum withdrawal amount is $10,000.00'}
        )
    
    def test_exact_boundary_amounts(self):
        """Test exact boundary amounts (min and max)"""
        # Test minimum valid amount
        min_data = self.valid_data.copy()
        min_data['amount'] = Decimal('1.00')
        self.assert_form_valid(WithdrawalRequestForm, min_data)
        
        # Test maximum valid amount
        max_data = self.valid_data.copy()
        max_data['amount'] = Decimal('10000.00')
        self.assert_form_valid(WithdrawalRequestForm, max_data)
    
    def test_required_fields(self):
        """Test that required fields are properly validated"""
        # Missing amount
        invalid_data = self.valid_data.copy()
        del invalid_data['amount']
        self.assert_form_invalid(WithdrawalRequestForm, invalid_data)
        
        # Missing withdrawal method
        invalid_data = self.valid_data.copy()
        del invalid_data['withdrawal_method']
        self.assert_form_invalid(WithdrawalRequestForm, invalid_data)
        
        # Missing account number
        invalid_data = self.valid_data.copy()
        del invalid_data['account_number']
        self.assert_form_invalid(WithdrawalRequestForm, invalid_data)
        
        # Missing account name
        invalid_data = self.valid_data.copy()
        del invalid_data['account_name']
        self.assert_form_invalid(WithdrawalRequestForm, invalid_data)
        
        # Missing bank name
        invalid_data = self.valid_data.copy()
        del invalid_data['bank_name']
        self.assert_form_invalid(WithdrawalRequestForm, invalid_data)
    
    def test_optional_bank_code(self):
        """Test that bank_code is optional"""
        optional_data = self.valid_data.copy()
        del optional_data['bank_code']
        
        form = self.assert_form_valid(WithdrawalRequestForm, optional_data)
        self.assertEqual(form.cleaned_data.get('bank_code', ''), '')
        
        # Empty bank code should also be valid
        optional_data['bank_code'] = ''
        form = self.assert_form_valid(WithdrawalRequestForm, optional_data)
    
    def test_withdrawal_method_choices(self):
        """Test withdrawal method choices"""
        valid_methods = ['paystack', 'flutterwave', 'bank_transfer']
        
        for method in valid_methods:
            method_data = self.valid_data.copy()
            method_data['withdrawal_method'] = method
            self.assert_form_valid(WithdrawalRequestForm, method_data)
        
        # Invalid withdrawal method
        invalid_data = self.valid_data.copy()
        invalid_data['withdrawal_method'] = 'invalid_method'
        self.assert_form_invalid(WithdrawalRequestForm, invalid_data)
    
    def test_form_widget_attributes(self):
        """Test form widget attributes and CSS classes"""
        form = WithdrawalRequestForm()
        
        # Check that all fields have proper CSS classes
        expected_class = 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent'
        
        for field_name in ['amount', 'withdrawal_method', 'account_number', 'account_name', 'bank_name', 'bank_code']:
            field_widget = form.fields[field_name].widget
            self.assertIn('class', field_widget.attrs)
            self.assertEqual(field_widget.attrs['class'], expected_class)
        
        # Check specific widget attributes
        amount_widget = form.fields['amount'].widget
        self.assertEqual(amount_widget.attrs['placeholder'], '0.00')
        self.assertEqual(amount_widget.attrs['step'], '0.01')
        self.assertEqual(amount_widget.attrs['min'], '1.00')
        
        # Check placeholders
        self.assertEqual(form.fields['account_number'].widget.attrs['placeholder'], 'Account Number')
        self.assertEqual(form.fields['account_name'].widget.attrs['placeholder'], 'Account Name')
        self.assertEqual(form.fields['bank_name'].widget.attrs['placeholder'], 'Bank Name')
        self.assertEqual(form.fields['bank_code'].widget.attrs['placeholder'], 'Bank Code (Optional)')
    
    def test_decimal_precision(self):
        """Test decimal precision handling"""
        # Test with various decimal precisions
        decimal_data = self.valid_data.copy()
        
        # Two decimal places (normal)
        decimal_data['amount'] = Decimal('123.45')
        form = self.assert_form_valid(WithdrawalRequestForm, decimal_data)
        
        # One decimal place
        decimal_data['amount'] = Decimal('123.5')
        form = self.assert_form_valid(WithdrawalRequestForm, decimal_data)
        self.assertEqual(form.cleaned_data['amount'], Decimal('123.5'))
        
        # No decimal places
        decimal_data['amount'] = Decimal('123')
        form = self.assert_form_valid(WithdrawalRequestForm, decimal_data)
        self.assertEqual(form.cleaned_data['amount'], Decimal('123'))
    
    def test_amount_type_coercion(self):
        """Test amount field type coercion"""
        # String that represents valid decimal
        string_data = self.valid_data.copy()
        string_data['amount'] = '123.45'
        form = self.assert_form_valid(WithdrawalRequestForm, string_data)
        self.assertEqual(form.cleaned_data['amount'], Decimal('123.45'))
        
        # Integer
        int_data = self.valid_data.copy()
        int_data['amount'] = 100
        form = self.assert_form_valid(WithdrawalRequestForm, int_data)
        self.assertEqual(form.cleaned_data['amount'], Decimal('100'))
    
    def test_clean_amount_custom_validation(self):
        """Test custom clean_amount method"""
        form = WithdrawalRequestForm(data=self.valid_data)
        form.is_valid()
        
        # Test the custom clean_amount method directly
        form.cleaned_data = {'amount': Decimal('0.50')}
        with self.assertRaisesMessage(
            Exception, 
            "Minimum withdrawal amount is $1.00"
        ):
            form.clean_amount()
        
        form.cleaned_data = {'amount': Decimal('10001.00')}
        with self.assertRaisesMessage(
            Exception,
            "Maximum withdrawal amount is $10,000.00"
        ):
            form.clean_amount()
        
        # Valid amount should pass
        form.cleaned_data = {'amount': Decimal('100.00')}
        result = form.clean_amount()
        self.assertEqual(result, Decimal('100.00'))


class FundWalletFormTest(WalletTestCase):
    """Test FundWalletForm functionality"""
    
    def setUp(self):
        super().setUp()
        self.valid_data = {
            'amount': Decimal('50.00'),
            'description': 'Test funding description'
        }
    
    def test_valid_form_data(self):
        """Test form with valid data"""
        form = self.assert_form_valid(FundWalletForm, self.valid_data)
        
        self.assertEqual(form.cleaned_data['amount'], Decimal('50.00'))
        self.assertEqual(form.cleaned_data['description'], 'Test funding description')
    
    def test_required_amount_field(self):
        """Test that amount field is required"""
        invalid_data = self.valid_data.copy()
        del invalid_data['amount']
        
        self.assert_form_invalid(FundWalletForm, invalid_data)
    
    def test_optional_description_field(self):
        """Test that description field is optional"""
        optional_data = self.valid_data.copy()
        del optional_data['description']
        
        form = self.assert_form_valid(FundWalletForm, optional_data)
        self.assertEqual(form.cleaned_data.get('description', ''), '')
        
        # Empty description should also be valid
        optional_data['description'] = ''
        form = self.assert_form_valid(FundWalletForm, optional_data)
    
    def test_minimum_amount_validation(self):
        """Test minimum amount validation"""
        invalid_data = self.valid_data.copy()
        invalid_data['amount'] = Decimal('0.00')
        
        self.assert_form_invalid(FundWalletForm, invalid_data)
        
        # Just below minimum
        invalid_data['amount'] = Decimal('0.001')
        self.assert_form_invalid(FundWalletForm, invalid_data)
    
    def test_minimum_valid_amount(self):
        """Test minimum valid amount"""
        min_data = self.valid_data.copy()
        min_data['amount'] = Decimal('0.01')
        
        form = self.assert_form_valid(FundWalletForm, min_data)
        self.assertEqual(form.cleaned_data['amount'], Decimal('0.01'))
    
    def test_decimal_field_constraints(self):
        """Test decimal field max_digits and decimal_places"""
        # Test maximum valid amount (12 digits total, 2 decimal places)
        max_data = self.valid_data.copy()
        max_data['amount'] = Decimal('9999999999.99')  # 10 + 2 = 12 digits
        
        form = self.assert_form_valid(FundWalletForm, max_data)
        self.assertEqual(form.cleaned_data['amount'], Decimal('9999999999.99'))
    
    def test_form_widget_attributes(self):
        """Test form widget attributes"""
        form = FundWalletForm()
        
        # Check amount field widget attributes
        amount_widget = form.fields['amount'].widget
        expected_class = 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent'
        self.assertEqual(amount_widget.attrs['class'], expected_class)
        self.assertEqual(amount_widget.attrs['placeholder'], '0.00')
        self.assertEqual(amount_widget.attrs['step'], '0.01')
        
        # Check description field widget attributes
        desc_widget = form.fields['description'].widget
        self.assertEqual(desc_widget.attrs['class'], expected_class)
        self.assertEqual(desc_widget.attrs['placeholder'], 'Description (optional)')
        self.assertEqual(desc_widget.attrs['rows'], 3)
    
    def test_large_description(self):
        """Test with large description text"""
        large_data = self.valid_data.copy()
        large_data['description'] = 'A' * 1000  # Large description
        
        # Should be valid (no max_length specified in CharField)
        self.assert_form_valid(FundWalletForm, large_data)
    
    def test_special_characters_in_description(self):
        """Test special characters in description"""
        special_data = self.valid_data.copy()
        special_data['description'] = 'Test with special chars: !@#$%^&*()[]{}|;:,.<>?'
        
        form = self.assert_form_valid(FundWalletForm, special_data)
        self.assertEqual(
            form.cleaned_data['description'],
            'Test with special chars: !@#$%^&*()[]{}|;:,.<>?'
        )
    
    def test_unicode_characters_in_description(self):
        """Test unicode characters in description"""
        unicode_data = self.valid_data.copy()
        unicode_data['description'] = 'Test with unicode: ñáéíóú €£¥'
        
        form = self.assert_form_valid(FundWalletForm, unicode_data)
        self.assertEqual(
            form.cleaned_data['description'],
            'Test with unicode: ñáéíóú €£¥'
        )
    
    def test_whitespace_handling(self):
        """Test whitespace handling in fields"""
        whitespace_data = {
            'amount': Decimal('50.00'),
            'description': '  Test with whitespace  '
        }
        
        form = self.assert_form_valid(FundWalletForm, whitespace_data)
        # Description should retain whitespace (no strip() applied)
        self.assertEqual(form.cleaned_data['description'], '  Test with whitespace  ')
    
    def test_negative_amount_validation(self):
        """Test that negative amounts are invalid"""
        negative_data = self.valid_data.copy()
        negative_data['amount'] = Decimal('-10.00')
        
        self.assert_form_invalid(FundWalletForm, negative_data)
    
    def test_zero_amount_validation(self):
        """Test that zero amount is invalid"""
        zero_data = self.valid_data.copy()
        zero_data['amount'] = Decimal('0.00')
        
        self.assert_form_invalid(FundWalletForm, zero_data)
    
    def test_form_field_types(self):
        """Test that form fields are of correct types"""
        form = FundWalletForm()
        
        from django import forms
        self.assertIsInstance(form.fields['amount'], forms.DecimalField)
        self.assertIsInstance(form.fields['description'], forms.CharField)
        
        # Check field parameters
        amount_field = form.fields['amount']
        self.assertEqual(amount_field.max_digits, 12)
        self.assertEqual(amount_field.decimal_places, 2)
        self.assertEqual(amount_field.min_value, Decimal('0.01'))
        
        # Check description field
        desc_field = form.fields['description']
        self.assertFalse(desc_field.required)
        self.assertIsInstance(desc_field.widget, forms.Textarea)


class FormIntegrationTest(BaseWalletTestCase):
    """Test form integration scenarios"""
    
    def test_form_model_integration(self):
        """Test that form data correctly maps to model fields"""
        form_data = {
            'amount': Decimal('150.00'),
            'withdrawal_method': 'bank_transfer',
            'account_number': '9876543210',
            'account_name': 'Integration Test Account',
            'bank_name': 'Integration Test Bank',
            'bank_code': '999'
        }
        
        form = WithdrawalRequestForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        # Create model instance from form
        withdrawal = form.save(commit=False)
        withdrawal.user = self.user
        withdrawal.save()
        
        # Verify model instance has correct data
        self.assertEqual(withdrawal.amount, Decimal('150.00'))
        self.assertEqual(withdrawal.withdrawal_method, 'bank_transfer')
        self.assertEqual(withdrawal.account_number, '9876543210')
        self.assertEqual(withdrawal.account_name, 'Integration Test Account')
        self.assertEqual(withdrawal.bank_name, 'Integration Test Bank')
        self.assertEqual(withdrawal.bank_code, '999')
        self.assertEqual(withdrawal.user, self.user)
    
    def test_form_error_display(self):
        """Test that form errors are properly formatted"""
        invalid_data = {
            'amount': Decimal('0.50'),  # Below minimum
            'withdrawal_method': 'invalid',  # Invalid choice
            'account_number': '',  # Required field missing
        }
        
        form = WithdrawalRequestForm(data=invalid_data)
        self.assertFalse(form.is_valid())
        
        # Check that errors exist for problematic fields
        self.assertIn('amount', form.errors)
        self.assertIn('withdrawal_method', form.errors)
        self.assertIn('account_number', form.errors)
        
        # Check specific error messages
        self.assertIn('Minimum withdrawal amount is $1.00', form.errors['amount'])
    
    def test_form_rendering_attributes(self):
        """Test that forms render with correct HTML attributes"""
        form = FundWalletForm()
        
        # Test that form renders without errors
        form_html = str(form)
        self.assertIn('class=', form_html)
        self.assertIn('placeholder=', form_html)
        
        # Test specific widget rendering
        amount_html = str(form['amount'])
        self.assertIn('step="0.01"', amount_html)
        self.assertIn('type="number"', amount_html)
        
        description_html = str(form['description'])
        self.assertIn('rows="3"', description_html)
        self.assertIn('<textarea', description_html)