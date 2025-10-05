# tasks/forms.py
from django import forms
from .models import Task, Submission, Dispute
from decimal import Decimal
from django.utils import timezone

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            'title',
            'description',
            'payout_per_slot',
            'total_slots',
            'deadline',
            'proof_instructions',
            'sample_image',     # ✅ new
            'sample_link',      # ✅ new
            'youtube_url',      # ✅ new
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'proof_instructions': forms.Textarea(attrs={'rows': 3}),
            'deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'payout_per_slot': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'total_slots': forms.NumberInput(),
            'sample_link': forms.URLInput(attrs={'placeholder': 'https://example.com'}),
            'youtube_url': forms.URLInput(attrs={'placeholder': 'https://youtube.com/watch?v=xxxx'}),
            "sample_image": forms.ClearableFileInput(attrs={"class": "file-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Force min slots
        self.fields['total_slots'].widget.attrs['min'] = '1'

    def clean_deadline(self):
        deadline = self.cleaned_data.get("deadline")
        if deadline and deadline <= timezone.now():
            raise forms.ValidationError("Deadline must be in the future.")
        return deadline


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['proof_text', 'proof_file', 'screenshot']
        widgets = {
            'proof_text': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe how you completed the task...'}),
        }


class TaskFilterForm(forms.Form):
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "class": "form-input",
        "placeholder": "Search tasks..."
    }))
    min_payout = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={
        "class": "form-input",
        "placeholder": "Min $"
    }))
    max_payout = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={
        "class": "form-input",
        "placeholder": "Max $"
    }))


class DisputeForm(forms.ModelForm):
    class Meta:
        model = Dispute
        fields = ['reason']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Explain why you are disputing this decision...'})
        }

class ReviewSubmissionForm(forms.Form):
    REVIEW_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ]
    
    decision = forms.ChoiceField(choices=REVIEW_CHOICES, widget=forms.RadioSelect)
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Reason for rejection (required if rejecting)...'})
    )




class TaskWalletTopupForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('1.00'),
        label="Amount to Transfer from Main Wallet"
    )
