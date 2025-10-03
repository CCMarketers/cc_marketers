# payments/forms.py
from django import forms
from decimal import Decimal
from .models import PaymentGateway


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
    # currency = forms.ChoiceField(
    #     choices=[("NGN", "Naira"), ("GHS", "Ghana Cedis"), ("KES", "Kenyan Shillings")],
    #     label="Currency",
    #     initial='Naira',
    #     widget=forms.Select(attrs={
    #         'class': 'w-full px-3 py-2 border border-red-300 rounded-md '
    #                  'focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent',
    #     })
    # )
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
    # gateway = forms.ChoiceField(
    #     choices=GATEWAY_CHOICES,
    #     initial='paystack',
    #     widget=forms.Select(attrs={'class': 'form-control'})
    # )
    gateway = forms.ChoiceField(choices=[
        (g.name.lower(), g.name) for g in PaymentGateway.objects.filter(is_active=True)
    ], initial='paystack',
        widget=forms.Select(attrs={'class': 'form-control'}))

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount < Decimal('100'):
            raise forms.ValidationError("Minimum withdrawal amount is ₦100")
        return amount


    def clean(self):
        cleaned = super().clean()
        gateway = cleaned.get("gateway", "").lower()
        if gateway in ["paystack", "flutterwave"]:
            if not cleaned.get("bank_code") or not cleaned.get("account_number"):
                raise forms.ValidationError("Bank details required for withdrawals.")
        return cleaned
