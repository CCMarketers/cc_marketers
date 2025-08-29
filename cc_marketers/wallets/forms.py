# wallets/forms.py
from django import forms
from decimal import Decimal
from .models import WithdrawalRequest

class WithdrawalRequestForm(forms.ModelForm):
    class Meta:
        model = WithdrawalRequest
        fields = ['amount', 'withdrawal_method', 'account_number', 'account_name', 'bank_name', 'bank_code']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '1.00'
            }),
            'withdrawal_method': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent'
            }),
            'account_number': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
                'placeholder': 'Account Number'
            }),
            'account_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
                'placeholder': 'Account Name'
            }),
            'bank_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
                'placeholder': 'Bank Name'
            }),
            'bank_code': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
                'placeholder': 'Bank Code (Optional)'
            }),
        }
    
    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount < Decimal('1.00'):
            raise forms.ValidationError("Minimum withdrawal amount is $1.00")
        if amount > Decimal('10000.00'):
            raise forms.ValidationError("Maximum withdrawal amount is $10,000.00")
        return amount

class FundWalletForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
            'placeholder': '0.00',
            'step': '0.01'
        })
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
            'placeholder': 'Description (optional)',
            'rows': 3
        })
    )