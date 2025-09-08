# apps/users/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from .models import User, UserProfile
from referrals.models import ReferralCode  # adjust import path

class CustomUserCreationForm(UserCreationForm):
    phone = forms.CharField(required=False, max_length=15)
    referral_code = forms.CharField(required=False, max_length=50)
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email address'
        })
    )
    phone = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '+234XXXXXXXXXX'
        })
    )
    first_name = forms.CharField(
        required=True,
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'First name'
        })
    )
    last_name = forms.CharField(
        required=True,
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Last name'
        })
    )
    referral_code = forms.CharField(
        required=False,
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Referral code (optional)'
        })
    )
    role = forms.ChoiceField(
        choices=User.ROLE_CHOICES,
        initial=User.MEMBER,
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'phone', 'password1', 'password2', 'referral_code', 'role')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'Create a password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-input',
            'placeholder': 'Confirm password'
        })
    
    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and User.objects.filter(phone=phone).exists():
            raise ValidationError('A user with this phone number already exists.')
        return phone
    
    def clean_referral_code(self):
        code = self.cleaned_data.get("referral_code")
        if code and not ReferralCode.objects.filter(code=code).exists():
            raise forms.ValidationError("Invalid referral code.")
        return code


    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data['phone']
        user.role = self.cleaned_data['role']
        
        if commit:
            user.save()
        return user

class CustomAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Email or phone number'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Password'
        })
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')

        # Try to find user by email or phone
        user = None
        if '@' in username:
            user = User.objects.filter(email=username).first()
        else:
            user = User.objects.filter(phone=username).first()

        if not user:
            raise forms.ValidationError("Invalid email or phone number.")

        # Always return email for authentication
        return user.email


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone', 'bio', 'avatar',
            'birth_date', 'country', 'state', 'city', 
            'receive_email_notifications', 'receive_sms_notifications'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'phone': forms.TextInput(attrs={'class': 'form-input'}),
            'bio': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'birth_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'country': forms.TextInput(attrs={'class': 'form-input'}),
            'state': forms.TextInput(attrs={'class': 'form-input'}),
            'city': forms.TextInput(attrs={'class': 'form-input'}),
            'receive_email_notifications': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'receive_sms_notifications': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

class ExtendedProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = [
            'occupation', 'company', 'website', 'twitter_url', 'location', 
            'linkedin_url', 'facebook_url', 'skills', 'experience_years'
        ]
        widgets = {
            'occupation': forms.TextInput(attrs={'class': 'form-input'}),
            'company': forms.TextInput(attrs={'class': 'form-input'}),
            'location': forms.TextInput(attrs={'class': 'form-input'}),
            'website': forms.URLInput(attrs={'class': 'form-input'}),
            'twitter_url': forms.URLInput(attrs={'class': 'form-input'}),
            'linkedin_url': forms.URLInput(attrs={'class': 'form-input'}),
            'facebook_url': forms.URLInput(attrs={'class': 'form-input'}),
            'skills': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'experience_years': forms.NumberInput(attrs={'class': 'form-input'}),
        }

class PhoneVerificationForm(forms.Form):
    phone = forms.CharField(
        max_length=17,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '+234XXXXXXXXXX'
        })
    )

class PhoneVerificationCodeForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '000000'
        })
    )

class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Current password'
        })
    )
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'New password'
        })
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm new password'
        })
    )
    
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise ValidationError('Current password is incorrect.')
        return current_password
    
    def clean(self):
        cleaned_data = super().clean()
        new_password1 = cleaned_data.get('new_password1')
        new_password2 = cleaned_data.get('new_password2')
        
        if new_password1 and new_password2 and new_password1 != new_password2:
            raise ValidationError('New passwords do not match.')
        
        return cleaned_data

