from django import forms
from decimal import Decimal
from .models import WithdrawalRequest


class WithdrawalRequestForm(forms.ModelForm):
    # ✅ Define bank_code at class level, not inside Meta
    bank_code = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
            'placeholder': 'Bank Code (Optional)'
        })
    )

    class Meta:
        model = WithdrawalRequest
        fields = ['amount_usd', 'withdrawal_method', 'account_number', 'account_name', 'bank_name', 'bank_code']
        widgets = {
            'amount_usd': forms.NumberInput(attrs={
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
        }

    def clean_amount_usd(self):
        amount_usd = self.cleaned_data['amount_usd']
        if amount_usd < Decimal('1.00'):  # match service minimum
            raise forms.ValidationError("Minimum withdrawal amount is $1.00")
        if amount_usd > Decimal('100000.00'):
            raise forms.ValidationError("Maximum withdrawal amount is $100,000.00")
        return amount_usd

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("withdrawal_method")

        if method == "bank_transfer":
            for field in ["account_number", "account_name", "bank_name"]:
                if not cleaned_data.get(field):
                    raise forms.ValidationError(f"{field.replace('_', ' ').title()} is required for bank transfer.")

        elif method == "crypto":
            if not cleaned_data.get("account_number"):
                raise forms.ValidationError("Wallet address is required for crypto withdrawals.")

        return cleaned_data



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
        strip=False,  # ✅ whitespace preserved
        widget=forms.Textarea(attrs={
            'class': 'w-full px-3 py-2 border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
            'placeholder': 'Description (optional)',
            'rows': 3
        })
    )

