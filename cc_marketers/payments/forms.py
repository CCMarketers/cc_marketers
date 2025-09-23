# payments/forms.py
from django import forms
from decimal import Decimal


# class WithdrawalForm(forms.Form):
#     """Form for wallet withdrawals"""
    
#     amount = forms.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         min_value=Decimal('100.00'),
#         widget=forms.NumberInput(attrs={
#             'class': 'w-full px-4 py-3 border border-red-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
#             'placeholder': 'Enter amount to withdraw',
#             'step': '0.01'
#         }),
#         help_text='Minimum withdrawal amount is ₦100'
#     )
    
#     bank_code = forms.CharField(
#         max_length=10,
#         widget=forms.Select(attrs={
#             'class': 'w-full px-4 py-3 border border-red-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
#             'id': 'bank_select'
#         }),
#         help_text='Select your bank'
#     )
    
#     account_number = forms.CharField(
#         max_length=20,
#         min_length=10,
#         widget=forms.TextInput(attrs={
#             'class': 'w-full px-4 py-3 border border-red-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
#             'placeholder': 'Enter your account number',
#             'id': 'account_number'
#         }),
#         help_text='Your 10-digit account number'
#     )
    
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         # Bank choices will be populated via JavaScript
#         self.fields['bank_code'].widget.choices = [('', 'Select Bank')]
    
#     def clean_amount(self):
#         amount = self.cleaned_data['amount']
#         if amount < Decimal('100.00'):
#             raise forms.ValidationError('Minimum withdrawal amount is ₦100')
#         return amount
    
#     def clean_account_number(self):
#         account_number = self.cleaned_data['account_number']
#         if not account_number.isdigit():
#             raise forms.ValidationError('Account number must contain only digits')
#         if len(account_number) != 10:
#             raise forms.ValidationError('Account number must be exactly 10 digits')
#         return account_number


# class FundingForm(forms.Form):
#     """Form for wallet funding"""
    
#     amount = forms.DecimalField(
#         max_digits=12,
#         decimal_places=2,
#         min_value=Decimal('100'),
#         widget=forms.NumberInput(attrs={
#             'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
#             'placeholder': '0.00',
#             'step': '0.01'
#         })
#     )
#     description = forms.CharField(
#         required=False,
#         widget=forms.Textarea(attrs={
#             'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
#             'placeholder': 'Description (optional)',
#             'rows': 3
#         })
#     )
    
#     def clean_amount(self):
#         amount = self.cleaned_data['amount']
#         if amount < Decimal('100.00'):
#             raise forms.ValidationError('Minimum funding amount is ₦100')
#         if amount > Decimal('1000000.00'):  # Maximum funding limit
#             raise forms.ValidationError('Maximum funding amount is ₦1,000,000')
#         return amount
    

# wallets/forms.py

GATEWAY_CHOICES = [
    ('paystack', 'Paystack'),
    ('flutterwave', 'Flutterwave'),
]

class FundingForm(forms.Form):
    """Form for wallet funding with Tailwind styling."""
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('50'),
        max_value=Decimal('1000000'),
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3 py-2 border border-red-300 rounded-md '
                     'focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
            'placeholder': 'Enter amount (Min: ₦50)',
            'step': '0.01',
        })
    )
    gateway = forms.ChoiceField(
        choices=GATEWAY_CHOICES,
        initial='paystack',
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-red-300 rounded-md '
                     'focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
        })
    )
    description = forms.CharField(
        required=False,
        strip=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-3 py-2 border border-red-300 rounded-md '
                     'focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
            'placeholder': 'Description (optional)',
            'rows': 3,
        })
    )

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount < Decimal('50'):
            raise forms.ValidationError("Minimum funding amount is ₦50")
        return amount


class WithdrawalForm(forms.Form):
    """Form for wallet withdrawal with gateway selection."""
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('100'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter amount (Min: ₦100)',
            'step': '0.01',
        })
    )
    bank_code = forms.CharField(
        max_length=10,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'bank-select'})
    )
    account_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter account number',
            'id': 'account-number'
        })
    )
    gateway = forms.ChoiceField(
        choices=GATEWAY_CHOICES,
        initial='paystack',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount < Decimal('100'):
            raise forms.ValidationError("Minimum withdrawal amount is ₦100")
        return amount

