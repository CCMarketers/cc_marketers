# tasks/forms.py
from django import forms
from .models import Task, Submission, Dispute

class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['title', 'description', 'payout_per_slot', 'total_slots', 'deadline', 'proof_instructions']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'proof_instructions': forms.Textarea(attrs={'rows': 3}),
            'deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'payout_per_slot': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
            'total_slots': forms.NumberInput(attrs={'min': '1'}),
        }

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
        "placeholder": "Min ₦"
    }))
    max_payout = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={
        "class": "form-input",
        "placeholder": "Max ₦"
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
