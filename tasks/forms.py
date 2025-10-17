# tasks/forms.py
from django import forms
from .models import Task, Submission, Dispute,TaskCategory
from decimal import Decimal
from django.utils import timezone
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile

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
            'sample_link',      
            'youtube_url',      
            'category',         
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'proof_instructions': forms.Textarea(attrs={'rows': 3}),
            'deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'payout_per_slot': forms.NumberInput(attrs={'step': '40.00', 'min': '40.00'}),
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
            'proof_text': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describe how you completed the task...'
            }),
        }

    MAX_SIZE = 10 * 1024 * 1024  # 10 MB

    def clean_proof_file(self):
        file = self.cleaned_data.get('proof_file')
        if not file:
            return file

        # Reject if file is too large and not an image
        if file.size > self.MAX_SIZE:
            if not file.content_type.startswith('image/'):
                raise forms.ValidationError("File too large. Maximum allowed size is 10MB.")

            # Try compressing image files
            return self._compress_image(file)
        return file

    def clean_screenshot(self):
        image = self.cleaned_data.get('screenshot')
        if not image:
            return image

        if image.size > self.MAX_SIZE:
            return self._compress_image(image)
        return image

    def _compress_image(self, image):
        """Helper to compress uploaded image to stay under MAX_SIZE."""
        try:
            img = Image.open(image)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            buffer = BytesIO()
            quality = 80
            img.save(buffer, format='JPEG', optimize=True, quality=quality)

            # Reduce quality until under limit or down to 40
            while buffer.tell() > self.MAX_SIZE and quality > 40:
                buffer.seek(0)
                buffer.truncate()
                quality -= 10
                img.save(buffer, format='JPEG', optimize=True, quality=quality)

            buffer.seek(0)
            compressed_file = InMemoryUploadedFile(
                buffer,
                image.field.name,
                f"compressed_{image.name.split('.')[0]}.jpg",
                'image/jpeg',
                buffer.tell(),
                None
            )
            return compressed_file
        except Exception as e:
            raise forms.ValidationError(f"Image compression failed: {e}")


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
    category = forms.ModelChoiceField(
        queryset=TaskCategory.objects.all(),
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={
            "class": "form-input"
        })
    )

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
