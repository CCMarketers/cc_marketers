# tests/test_forms.py
from django.test import TestCase
from django.contrib.auth import get_user_model

from users.forms import (
    CustomUserCreationForm, CustomAuthenticationForm, UserProfileForm,
    ExtendedProfileForm, PhoneVerificationForm, PhoneVerificationCodeForm,
    PasswordChangeForm
)
# from users.models import UserProfile
from referrals.models import ReferralCode

User = get_user_model()


class CustomUserCreationFormTest(TestCase):
    """Test CustomUserCreationForm"""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123"
        )
        # If referral codes are auto-created by a signal, just grab it
        self.referral_code = getattr(self.user, "referral_code", None)

        # Or if not auto-created, create manually:
        if not self.referral_code:
            self.referral_code = ReferralCode.objects.create(
                user=self.user, code="TEST123"
            )
        self.valid_data = {
            'email': 'newuser@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'phone': '+1234567890',
            'password1': 'testpass123!',
            'password2': 'testpass123!',
            'referral_code': '',
            'role': User.MEMBER,
        }

    def test_form_valid_data(self):
        """Test form with valid data"""
        form = CustomUserCreationForm(data=self.valid_data)
        self.assertTrue(form.is_valid())

    def test_form_save(self):
        """Test form save creates user with correct data"""
        form = CustomUserCreationForm(data=self.valid_data)
        self.assertTrue(form.is_valid())
        
        user = form.save()
        self.assertEqual(user.email, 'newuser@example.com')
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertEqual(user.phone, '+1234567890')
        self.assertEqual(user.role, User.MEMBER)
        self.assertTrue(user.check_password('testpass123!'))

    def test_duplicate_email_validation(self):
        """Test validation for duplicate email"""
        data = self.valid_data.copy()
        data['email'] = 'test@example.com'  # existing user’s email
        form = CustomUserCreationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        self.assertEqual(
            form.errors['email'][0],
            'A user with this email already exists.'
        )


    def test_duplicate_phone_validation(self):
        """Test validation for duplicate phone"""
        # Create existing user with same phone
        User.objects.create_user(
            email='existing@example.com',
            phone='+1234567890',
            password='pass123'
        )
        
        form = CustomUserCreationForm(data=self.valid_data)
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)
        self.assertEqual(
            form.errors['phone'][0],
            'A user with this phone number already exists.'
        )

    def test_phone_field_optional(self):
        """Test phone field is optional"""
        data = self.valid_data.copy()
        data['phone'] = ''
        
        form = CustomUserCreationForm(data=data)
        self.assertTrue(form.is_valid())

    def test_valid_referral_code(self):
        """Test form with valid referral code"""
        data = self.valid_data.copy()
        data['referral_code'] = self.referral_code.code

        
        form = CustomUserCreationForm(data=data)
        self.assertTrue(form.is_valid())

    def test_invalid_referral_code(self):
        """Test form with invalid referral code"""
        data = self.valid_data.copy()
        data['referral_code'] = 'INVALID'
        
        form = CustomUserCreationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('referral_code', form.errors)
        self.assertEqual(
            form.errors['referral_code'][0],
            'Invalid referral code.'
        )

    def test_empty_referral_code(self):
        """Test form with empty referral code is valid"""
        data = self.valid_data.copy()
        data['referral_code'] = ''
        
        form = CustomUserCreationForm(data=data)
        self.assertTrue(form.is_valid())

    def test_password_mismatch(self):
        """Test password mismatch validation"""
        data = self.valid_data.copy()
        data['password2'] = 'differentpass'
        
        form = CustomUserCreationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_required_fields(self):
        """Test required fields validation"""
        required_fields = ['email', 'first_name', 'last_name', 'password1', 'password2']
        
        for field in required_fields:
            data = self.valid_data.copy()
            data[field] = ''
            
            form = CustomUserCreationForm(data=data)
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_form_widgets_have_correct_classes(self):
        """Test form widgets have correct CSS classes"""
        form = CustomUserCreationForm()
        
        expected_widgets = [
            'email', 'first_name', 'last_name', 'phone',
            'password1', 'password2', 'referral_code', 'role'
        ]
        
        for field_name in expected_widgets:
            widget = form.fields[field_name].widget
            if hasattr(widget, 'attrs'):
                self.assertIn('class', widget.attrs)
                self.assertEqual(widget.attrs['class'], 'form-input')


class CustomAuthenticationFormTest(TestCase):
    """Test CustomAuthenticationForm"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            phone='+1234567890',
            password='testpass123'
        )

    def test_login_with_email(self):
        """Test login with email"""
        form_data = {
            'username': 'test@example.com',
            'password': 'testpass123'
        }
        
        form = CustomAuthenticationForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_login_with_phone(self):
        """Test login with phone number"""
        form_data = {
            'username': '+1234567890',
            'password': 'testpass123'
        }
        
        form = CustomAuthenticationForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_clean_username_with_email(self):
        """Test clean_username method with email"""
        form_data = {
            'username': 'test@example.com',
            'password': 'testpass123'
        }
        
        form = CustomAuthenticationForm(data=form_data)
        form.is_valid()
        self.assertEqual(form.cleaned_data['username'], 'test@example.com')

    def test_clean_username_with_phone(self):
        """Test clean_username method with phone"""
        form_data = {
            'username': '+1234567890',
            'password': 'testpass123'
        }
        
        form = CustomAuthenticationForm(data=form_data)
        form.is_valid()
        # Should return email even when phone is provided
        self.assertEqual(form.cleaned_data['username'], 'test@example.com')

    def test_clean_username_nonexistent_email(self):
        """Test clean_username with nonexistent email"""
        form_data = {
            'username': 'nonexistent@example.com',
            'password': 'testpass123'
        }
        
        form = CustomAuthenticationForm(data=form_data)
        form.is_valid()
        # Should return original input if user not found
        self.assertEqual(form.cleaned_data['username'], 'nonexistent@example.com')

    def test_clean_username_nonexistent_phone(self):
        """Test clean_username with nonexistent phone"""
        form_data = {
            'username': '+9999999999',
            'password': 'testpass123'
        }
        
        form = CustomAuthenticationForm(data=form_data)
        form.is_valid()
        # Should return original input if user not found
        self.assertEqual(form.cleaned_data['username'], '+9999999999')

    def test_invalid_credentials(self):
        """Test form with invalid credentials"""
        form_data = {
            'username': 'test@example.com',
            'password': 'wrongpassword'
        }
        
        form = CustomAuthenticationForm(data=form_data)
        self.assertFalse(form.is_valid())

    def test_form_widgets_have_correct_classes(self):
        """Test form widgets have correct CSS classes"""
        form = CustomAuthenticationForm()
        
        self.assertEqual(
            form.fields['username'].widget.attrs['class'],
            'form-input'
        )
        self.assertEqual(
            form.fields['password'].widget.attrs['class'],
            'form-input'
        )


class UserProfileFormTest(TestCase):
    """Test UserProfileForm"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_form_fields(self):
        """Test form includes correct fields"""
        form = UserProfileForm()
        expected_fields = [
            'first_name', 'last_name', 'phone', 'bio', 'avatar',
            'birth_date', 'country', 'state', 'city',
            'receive_email_notifications', 'receive_sms_notifications'
        ]
        
        for field in expected_fields:
            self.assertIn(field, form.fields)

    def test_form_valid_data(self):
        """Test form with valid data"""
        form_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone': '+1234567890',
            'bio': 'Software developer',
            'birth_date': '1990-01-01',
            'country': 'Nigeria',
            'state': 'Lagos',
            'city': 'Lagos',
            'receive_email_notifications': True,
            'receive_sms_notifications': False
        }
        
        form = UserProfileForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_form_save(self):
        """Test form saves data correctly"""
        form_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'phone': '+1234567890',
            'bio': 'Software developer',
            'country': 'Nigeria',
            'receive_email_notifications': True,
            'receive_sms_notifications': False
        }
        
        form = UserProfileForm(instance=self.user, data=form_data)
        self.assertTrue(form.is_valid())
        
        user = form.save()
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
        self.assertEqual(user.phone, '+1234567890')
        self.assertEqual(user.bio, 'Software developer')
        self.assertEqual(user.country, 'Nigeria')
        self.assertTrue(user.receive_email_notifications)
        self.assertFalse(user.receive_sms_notifications)

    def test_form_widgets_have_correct_classes(self):
        """Test form widgets have correct CSS classes"""
        form = UserProfileForm()
        
        text_fields = ['first_name', 'last_name', 'phone', 'country', 'state', 'city']
        for field_name in text_fields:
            self.assertEqual(
                form.fields[field_name].widget.attrs['class'],
                'form-input'
            )
        
        self.assertEqual(
            form.fields['bio'].widget.attrs['class'],
            'form-input'
        )
        # self.assertEqual(
        #     form.fields['birth_date'].widget.attrs['type'],
        #     'date'
        # )
        widget = form.fields['birth_date'].widget
        self.assertEqual(
            widget.input_type,
            'date'
        )


class ExtendedProfileFormTest(TestCase):
    """Test ExtendedProfileForm"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.profile = self.user.profile


    def test_form_fields(self):
        """Test form includes correct fields"""
        form = ExtendedProfileForm()
        expected_fields = [
            'occupation', 'company', 'website', 'twitter_url',
            'linkedin_url', 'facebook_url', 'skills', 'experience_years'
        ]
        
        for field in expected_fields:
            self.assertIn(field, form.fields)

    def test_form_valid_data(self):
        """Test form with valid data"""
        form_data = {
            'occupation': 'Software Developer',
            'company': 'Tech Corp',
            'website': 'https://example.com',
            'twitter_url': 'https://twitter.com/user',
            'linkedin_url': 'https://linkedin.com/in/user',
            'facebook_url': 'https://facebook.com/user',
            'skills': 'Python, Django, JavaScript',
            'experience_years': 5
        }
        
        form = ExtendedProfileForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_form_save(self):
        """Test form saves data correctly"""
        form_data = {
            'occupation': 'Software Developer',
            'company': 'Tech Corp',
            'website': 'https://example.com',
            'skills': 'Python, Django',
            'experience_years': 5
        }
        
        form = ExtendedProfileForm(instance=self.profile, data=form_data)
        self.assertTrue(form.is_valid())
        
        profile = form.save()
        self.assertEqual(profile.occupation, 'Software Developer')
        self.assertEqual(profile.company, 'Tech Corp')
        self.assertEqual(profile.website, 'https://example.com')
        self.assertEqual(profile.skills, 'Python, Django')
        self.assertEqual(profile.experience_years, 5)

    def test_invalid_url_fields(self):
        """Test validation for URL fields"""
        url_fields = ['website', 'twitter_url', 'linkedin_url', 'facebook_url']
        
        for field in url_fields:
            form_data = {field: 'invalid-url'}
            form = ExtendedProfileForm(data=form_data)
            self.assertFalse(form.is_valid())
            self.assertIn(field, form.errors)

    def test_valid_url_fields(self):
        """Test valid URLs are accepted"""
        form_data = {
            'website': 'https://example.com',
            'twitter_url': 'https://twitter.com/user',
            'linkedin_url': 'https://linkedin.com/in/user',
            'facebook_url': 'https://facebook.com/user'
        }
        
        form = ExtendedProfileForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_negative_experience_years(self):
        """Test negative experience years validation"""
        form_data = {'experience_years': -1}
        form = ExtendedProfileForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('experience_years', form.errors)


class PhoneVerificationFormTest(TestCase):
    """Test PhoneVerificationForm"""

    def test_valid_phone_number(self):
        """Test form with valid phone number"""
        form_data = {'phone': '+1234567890'}
        form = PhoneVerificationForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_empty_phone_number(self):
        """Test form with empty phone number"""
        form_data = {'phone': ''}
        form = PhoneVerificationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_phone_max_length(self):
        """Test phone number max length validation"""
        form_data = {'phone': '+' + '1' * 20}  # Too long
        form = PhoneVerificationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_form_widget_has_correct_class(self):
        """Test form widget has correct CSS class"""
        form = PhoneVerificationForm()
        self.assertEqual(
            form.fields['phone'].widget.attrs['class'],
            'form-input'
        )


class PhoneVerificationCodeFormTest(TestCase):
    """Test PhoneVerificationCodeForm"""

    def test_valid_code(self):
        """Test form with valid 6-digit code"""
        form_data = {'code': '123456'}
        form = PhoneVerificationCodeForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_empty_code(self):
        """Test form with empty code"""
        form_data = {'code': ''}
        form = PhoneVerificationCodeForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)

    def test_short_code(self):
        """Test form with code less than 6 digits"""
        form_data = {'code': '12345'}
        form = PhoneVerificationCodeForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)

    def test_long_code(self):
        """Test form with code more than 6 digits"""
        form_data = {'code': '1234567'}
        form = PhoneVerificationCodeForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)

    def test_non_numeric_code(self):
        """Test form accepts non-numeric codes (validation handled elsewhere)"""
        form_data = {'code': 'abc123'}
        form = PhoneVerificationCodeForm(data=form_data)
        self.assertTrue(form.is_valid())  # Form validation passes, business logic validates

    def test_form_widget_has_correct_class(self):
        """Test form widget has correct CSS class"""
        form = PhoneVerificationCodeForm()
        self.assertEqual(
            form.fields['code'].widget.attrs['class'],
            'form-input'
        )


class PasswordChangeFormTest(TestCase):
    """Test PasswordChangeForm"""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='oldpassword123'
        )

    def test_valid_password_change(self):
        """Test form with valid password change data"""
        form_data = {
            'current_password': 'oldpassword123',
            'new_password1': 'newpassword456',
            'new_password2': 'newpassword456'
        }
        
        form = PasswordChangeForm(user=self.user, data=form_data)
        self.assertTrue(form.is_valid())

    def test_incorrect_current_password(self):
        """Test form with incorrect current password"""
        form_data = {
            'current_password': 'wrongpassword',
            'new_password1': 'newpassword456',
            'new_password2': 'newpassword456'
        }
        
        form = PasswordChangeForm(user=self.user, data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('current_password', form.errors)
        self.assertEqual(
            form.errors['current_password'][0],
            'Current password is incorrect.'
        )

    def test_password_mismatch(self):
        """Test form with password mismatch"""
        form_data = {
            'current_password': 'oldpassword123',
            'new_password1': 'newpassword456',
            'new_password2': 'differentpassword'
        }
        
        form = PasswordChangeForm(user=self.user, data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)
        self.assertEqual(
            form.errors['__all__'][0],
            'New passwords do not match.'
        )

    def test_empty_current_password(self):
        """Test form with empty current password"""
        form_data = {
            'current_password': '',
            'new_password1': 'newpassword456',
            'new_password2': 'newpassword456'
        }
        
        form = PasswordChangeForm(user=self.user, data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('current_password', form.errors)

    def test_empty_new_passwords(self):
        """Test form with empty new passwords"""
        form_data = {
            'current_password': 'oldpassword123',
            'new_password1': '',
            'new_password2': ''
        }
        
        form = PasswordChangeForm(user=self.user, data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('new_password1', form.errors)
        self.assertIn('new_password2', form.errors)

    def test_form_requires_user_instance(self):
        """Test form requires user instance"""
        form_data = {
            'current_password': 'oldpassword123',
            'new_password1': 'newpassword456',
            'new_password2': 'newpassword456'
        }
        
        # Should raise TypeError when user is not provided
        with self.assertRaises(TypeError):
            PasswordChangeForm(data=form_data)

    def test_form_widgets_have_correct_classes(self):
        """Test form widgets have correct CSS classes"""
        form = PasswordChangeForm(user=self.user)
        
        password_fields = ['current_password', 'new_password1', 'new_password2']
        for field_name in password_fields:
            self.assertEqual(
                form.fields[field_name].widget.attrs['class'],
                'form-input'
            )

    def test_clean_method_with_partial_data(self):
        """Test clean method with partial form data"""
        form_data = {
            'current_password': 'oldpassword123',
            'new_password1': 'newpassword456'
            # Missing new_password2
        }
        
        form = PasswordChangeForm(user=self.user, data=form_data)
        self.assertFalse(form.is_valid())
        # Should not raise exception even with missing data


class FormsWidgetTest(TestCase):
    """Test form widget attributes and styling"""

    def test_all_forms_have_consistent_styling(self):
        """Test all forms use consistent CSS classes"""
        forms_to_test = [
            CustomUserCreationForm(),
            CustomAuthenticationForm(),
            UserProfileForm(),
            ExtendedProfileForm(),
            PhoneVerificationForm(),
            PhoneVerificationCodeForm(),
            PasswordChangeForm(user=User(email='test@example.com'))
        ]
        
        for form in forms_to_test:
            for field_name, field in form.fields.items():
                if hasattr(field.widget, 'attrs') and 'class' in field.widget.attrs:
                    # Most form fields should use 'form-input' class
                    expected_classes = ['form-input', 'form-checkbox']
                    self.assertIn(
                        field.widget.attrs['class'],
                        expected_classes,
                        f"Field {field_name} in {form.__class__.__name__} has unexpected class"
                    )

    def test_placeholder_texts_are_meaningful(self):
        """Test form fields have meaningful placeholder texts"""
        form = CustomUserCreationForm()
        
        placeholder_checks = {
            'email': 'Enter your email address',
            'phone': '+234XXXXXXXXXX',
            'first_name': 'First name',
            'last_name': 'Last name',
            'referral_code': 'Referral code (optional)'
        }
        
        for field_name, expected_placeholder in placeholder_checks.items():
            widget = form.fields[field_name].widget
            if hasattr(widget, 'attrs') and 'placeholder' in widget.attrs:
                self.assertEqual(
                    widget.attrs['placeholder'],
                    expected_placeholder,
                    f"Field {field_name} has incorrect placeholder"
                )

    def test_password_fields_use_password_widget(self):
        """Test password fields use PasswordInput widget"""
        from django.forms.widgets import PasswordInput
        
        forms_with_passwords = [
            (CustomUserCreationForm(), ['password1', 'password2']),
            (CustomAuthenticationForm(), ['password']),
            (PasswordChangeForm(user=User(email='test@example.com')), 
             ['current_password', 'new_password1', 'new_password2'])
        ]
        
        for form, password_fields in forms_with_passwords:
            for field_name in password_fields:
                self.assertIsInstance(
                    form.fields[field_name].widget,
                    PasswordInput,
                    f"Field {field_name} should use PasswordInput widget"
                )