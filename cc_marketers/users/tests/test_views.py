from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.contrib import messages
from django.contrib.auth import get_user_model

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

# Import models from related apps that the views touch
from users.models import UserProfile, EmailVerificationToken, PhoneVerificationToken
from referrals.models import  Referral
from tasks.models import Task, Submission
from wallets.models import WithdrawalRequest, Transaction

from django.core import mail # <-- Import mail

User = get_user_model()


@override_settings(PASSWORD_HASHERS=[
    'django.contrib.auth.hashers.MD5PasswordHasher',
])
class BaseUsersViewTest(TestCase):
    """Shared helpers & fixtures for users view tests (DRY)."""

    @classmethod
    def setUpTestData(cls):
        cls.password = "P@ssw0rd!"
        cls.member = cls._make_user(
            email="member@example.com",
            role=User.MEMBER,
            first_name="Mem",
            last_name="Ber",
        )
        cls.advertiser = cls._make_user(
            email="adv@example.com",
            role=User.ADVERTISER,
            first_name="Ad",
            last_name="Vert",
        )
        cls.admin = cls._make_user(
            email="admin@example.com",
            role=User.ADMIN,
            first_name="Ad",
            last_name="Min",
            is_staff=True,
        )

        # A referral code for the admin
        cls.ref_code = cls.admin.referral_code.code
        
        # self.referral_code = 

    @classmethod
    def _make_user(cls, email: str, role: str, first_name="", last_name="", is_staff=False):
        u = User.objects.create(
            email=email,
            role=role,
            first_name=first_name,
            last_name=last_name,
            is_staff=is_staff,
        )
        u.set_password(cls.password)
        # ensure username exists in case View logic depends on it
        if not u.username:
            u.username = email.split("@")[0]
        u.save()
        return u

    def login(self, user):
        c = Client()
        ok = c.login(username=user.email, password=self.password)
        self.assertTrue(ok, "Login should succeed in tests")
        return c


class TestUserRegistrationView(BaseUsersViewTest):
    def test_get_prefills_referral_code(self):
        url = reverse('users:register') + '?ref=REFADMIN'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)
        self.assertEqual(resp.context['form'].initial.get('referral_code'), 'REFADMIN')

    @patch('users.views.send_verification_email', return_value=True)
    def test_post_creates_user_tracks_referral_logs_in_and_sends_email(self, mock_send):
        url = reverse('users:register')
        payload = {
            'email': 'newuser@example.com',
            'first_name': 'New',         # <-- ADDED
            'last_name': 'User',          # <-- ADDED
            'password1': 'StrongPass123!@#',
            'password2': 'StrongPass123!@#',
            'role': User.MEMBER,
            'referral_code': self.ref_code, # Use the valid code from setup
        }
        resp = self.client.post(url, data=payload, follow=True)
        self.assertEqual(resp.status_code, 200)
        
        # Now this will pass
        new_user = User.objects.get(email='newuser@example.com')
        self.assertTrue(resp.context['user'].is_authenticated)
        
        self.assertTrue(Referral.objects.filter(referrer=self.admin, referred=new_user, level=1).exists())
        mock_send.assert_called_once_with(new_user)
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('verify your email' in m.message.lower() for m in msgs))
    
    # users/tests/test_views.py (Corrected)
    @patch('users.views.send_verification_email', return_value=True)
    def test_post_with_invalid_referral_code_fails_validation(self, mock_send_email):
        """
        Test that an invalid referral code causes a form validation error
        and prevents user creation.
        """
        url = reverse('users:register')
        payload = {
            'email': 'noref@example.com',
            'first_name': 'No',
            'last_name': 'Ref',
            'password1': 'StrongPass123!@#',
            'password2': 'StrongPass123!@#',
            'role': User.MEMBER,
            'referral_code': 'NOTREAL',
        }
        
        # Make the POST request but DO NOT follow redirects.
        # An invalid form does not redirect.
        resp = self.client.post(url, data=payload)

        # 1. Assert the page was re-rendered successfully (status code 200)
        self.assertEqual(resp.status_code, 200)

        # 2. Assert that the form in the context has an error for the 'referral_code' field
        self.assertIn('form', resp.context)
        self.assertTrue(resp.context['form'].is_bound)
        self.assertIn('referral_code', resp.context['form'].errors)

        # 3. The most important check: assert that NO user was created.
        self.assertFalse(User.objects.filter(email='noref@example.com').exists())
        
        # 4. Assert the mock email function was NOT called
        mock_send_email.assert_not_called()

class TestCustomLoginLogoutViews(BaseUsersViewTest):
    def test_login_redirects_by_role_member(self):
        url = reverse('users:login')
        resp = self.client.post(url, data={'username': self.member.email, 'password': self.password})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('tasks:task_list'))

    def test_login_redirects_by_role_advertiser(self):
        url = reverse('users:login')
        resp = self.client.post(url, data={'username': self.advertiser.email, 'password': self.password})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('tasks:my_tasks'))

    def test_login_redirects_by_role_admin(self):
        url = reverse('users:login')
        resp = self.client.post(url, data={'username': self.admin.email, 'password': self.password})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], reverse('users:dashboard'))

    def test_login_invalid(self):
        url = reverse('users:login')
        resp = self.client.post(url, data={'username': self.member.email, 'password': 'wrong'})
        self.assertEqual(resp.status_code, 200)
        # message added
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('invalid login credentials' in m.message.lower() for m in msgs))

    def test_logout_redirects_with_message(self):
        c = self.login(self.member)
        url = reverse('users:logout')
        resp = c.get(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.redirect_chain[-1][0], reverse('users:login'))
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('logged out' in m.message.lower() for m in msgs))


class TestProfileSetupView(BaseUsersViewTest):
    def test_requires_login(self):
        url = reverse('users:profile_setup')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_get_creates_extended_profile(self):
        c = self.login(self.member)
        url = reverse('users:profile_setup')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=self.member).exists())
        self.assertIn('extended_profile', resp.context)

    def test_post_updates_user_and_extended_profile(self):
        c = self.login(self.member)
        url = reverse('users:profile_setup')
        data = {
            'first_name': 'New',
            'last_name': 'Name',
            'location': 'Lagos',
            'skills': 'Django,Testing',
        }
        resp = c.post(url, data=data, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, 'New')
        profile = UserProfile.objects.get(user=self.member)
        self.assertEqual(profile.location, 'Lagos')
        self.assertEqual(profile.skills, 'Django,Testing')


class TestUserDashboardView(BaseUsersViewTest):
    @patch('users.views.WalletService.get_or_create_wallet')
    def test_dashboard_context_and_balances(self, mock_wallet_svc):
        # Create submissions & tasks
        from datetime import timedelta

        t1 = Task.objects.create(
            title='Task 1',
            advertiser=self.advertiser,
            status='active',
            payout_per_slot=Decimal('5.00'),
            total_slots=10,
            deadline=timezone.now() + timedelta(days=7),  # 👈 add deadline
        )
        t2 = Task.objects.create(
            title='Task 2',
            advertiser=self.advertiser,
            status='active',
            payout_per_slot=Decimal('6.00'),
            total_slots=11,
            deadline=timezone.now() + timedelta(days=7),  # 👈 add deadline
        )
        

        Submission.objects.create(task=t1, member=self.member, status='approved', submitted_at=timezone.now())
        Submission.objects.create(task=t2, member=self.member, status='pending', submitted_at=timezone.now())

        # Wallet mock
        wallet = MagicMock()
        wallet.get_available_balance.return_value = Decimal('100.00')
        mock_wallet_svc.return_value = wallet

        # Pending withdrawal and transactions
        WithdrawalRequest.objects.create(user=self.member, amount=Decimal('25.00'), status='pending')
        Transaction.objects.create(
            user=self.member, 
            amount=Decimal('10.00'), 
            transaction_type='credit',
            balance_before=Decimal('0.00'),
            balance_after=Decimal('10.00')   # <-- FIX
        )
        c = self.login(self.member)
        url = reverse('users:dashboard')
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertIn('user_stats', ctx)
        self.assertIn('recent_tasks', ctx)
        self.assertIn('completed_tasks_count', ctx)
        self.assertIn('active_tasks_count', ctx)
        self.assertIn('referral_code', ctx)
        self.assertIn('referral_link', ctx)
        self.assertIn('recent_transactions', ctx)
        # available_balance = 100 - 25
        self.assertEqual(ctx['available_balance'], Decimal('75.00'))


# users/tests/test_views.py (Corrected)

class TestEmailVerificationFlow(BaseUsersViewTest):
    def test_email_verification_valid_token_sets_flag_and_redirects(self):
        # Ensure we have a fresh user instance from the DB before making the token
        member_fresh = User.objects.get(pk=self.member.pk) # <-- RE-FETCH USER
        uidb64 = urlsafe_base64_encode(force_bytes(member_fresh.pk))
        token = self._make_valid_token(member_fresh)
        url = reverse('users:verify_email', kwargs={'uidb64': uidb64, 'token': token})

        # when not authenticated → redirect to login
        resp = self.client.get(url, follow=True)
        self.member.refresh_from_db()
        self.assertTrue(self.member.email_verified) # <-- This should now pass
        self.assertEqual(resp.redirect_chain[-1][0], reverse('users:login'))

        # when authenticated → redirect to dashboard
        c = self.login(self.member) # This login updates the `last_login` field
        self.member.email_verified = False
        self.member.save(update_fields=["email_verified"])
        
        # Re-fetch again after login to get the updated state
        member_after_login = User.objects.get(pk=self.member.pk) # <-- RE-FETCH USER
        token = self._make_valid_token(member_after_login)
        url = reverse('users:verify_email', kwargs={'uidb64': uidb64, 'token': token})
        resp2 = c.get(url, follow=True)
        self.member.refresh_from_db()
        self.assertTrue(self.member.email_verified)
        self.assertEqual(resp2.redirect_chain[-1][0], reverse('users:dashboard'))
    


    def test_email_verification_invalid_token_renders_error(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.member.pk))
        url = reverse('users:verify_email', kwargs={'uidb64': uidb64, 'token': 'invalid'})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('invalid' in m.message.lower() for m in msgs))

    def _make_valid_token(self, user):
        from django.contrib.auth.tokens import default_token_generator
        return default_token_generator.make_token(user)


class TestResendVerificationView(BaseUsersViewTest):
    @patch('users.views.send_verification_email', return_value=True)
    def test_resend_when_not_verified(self, mock_send):
        self.member.email_verified = False
        self.member.save(update_fields=["email_verified"])
        c = self.login(self.member)
        # Create some stale tokens to ensure they are cleared
        EmailVerificationToken.objects.create(user=self.member, used=False)
        EmailVerificationToken.objects.create(user=self.member, used=False)
        url = reverse('users:resend_verification')
        resp = c.post(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(EmailVerificationToken.objects.filter(user=self.member, used=False).count(), 0)
        mock_send.assert_called_once_with(self.member)
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('sent' in m.message.lower() for m in msgs))

    @patch('users.views.send_verification_email', return_value=True)
    def test_resend_when_already_verified(self, _):
        self.member.email_verified = True
        self.member.save(update_fields=["email_verified"])
        c = self.login(self.member)
        url = reverse('users:resend_verification')
        resp = c.post(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('already verified' in m.message.lower() for m in msgs))

    @patch('users.views.send_verification_email', return_value=False)
    def test_resend_handles_send_failure(self, _):
        self.member.email_verified = False
        self.member.save(update_fields=["email_verified"])
        c = self.login(self.member)
        url = reverse('users:resend_verification')
        resp = c.post(url, follow=True)
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('failed' in m.message.lower() for m in msgs))


class TestPhoneVerificationViews(BaseUsersViewTest):
    def test_phone_verification_flow(self):
        c = self.login(self.member)
        # Step 1: submit phone
        url = reverse('users:phone_verify')
        resp = c.post(url, data={'phone': '+2348123456789'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.phone, '+2348123456789')
        # Token created
        self.assertTrue(PhoneVerificationToken.objects.filter(user=self.member, used=False).exists())

        # Grab token and verify
        token = PhoneVerificationToken.objects.filter(user=self.member, used=False).latest('created_at')
        url2 = reverse('users:phone_verify_code')
        resp2 = c.post(url2, data={'code': token.token}, follow=True)
        self.member.refresh_from_db()
        token.refresh_from_db()
        self.assertTrue(self.member.phone_verified)
        self.assertTrue(token.used)
        msgs = list(messages.get_messages(resp2.wsgi_request))
        self.assertTrue(any('phone verified' in m.message.lower() for m in msgs))

    def test_phone_verification_invalid_code(self):
        c = self.login(self.member)
        # ensure at least one token exists but post wrong code
        PhoneVerificationToken.objects.create(user=self.member)
        url2 = reverse('users:phone_verify_code')
        resp = c.post(url2, data={'code': 'WRONG'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        form = resp.context['form']
        self.assertIn('code', form.errors)


class TestPasswordChangeView(BaseUsersViewTest):
    def test_password_change_success(self):
        c = self.login(self.member)
        url = reverse('users:password_change')
        # The custom form in views expects new_password1; we'll submit matching fields
        data = {
            'current_password': self.password,   # old password
            'new_password1': 'N3w-Secret-123',
            'new_password2': 'N3w-Secret-123'
        }

        resp = c.post(url, data=data, follow=True)
        self.assertEqual(resp.status_code, 200)
        # Verify that the new password works
        c.logout()
        ok = c.login(username=self.member.email, password='N3w-Secret-123')
        self.assertTrue(ok)
        msgs = list(messages.get_messages(resp.wsgi_request))
        self.assertTrue(any('password changed' in m.message.lower() for m in msgs))



class TestCustomPasswordResetView(BaseUsersViewTest):
    def test_send_mail_renders_and_sends(self):
        url = reverse('users:password_reset')
        resp = self.client.post(url, data={'email': self.member.email}, follow=True)
        
        # Check that the view redirected to the success page
        self.assertEqual(resp.status_code, 200)
        self.assertRedirects(resp, reverse('users:password_reset_done'))

        # Check that one email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        
        # Check email details
        self.assertEqual(email.to, [self.member.email])
        self.assertIn("Password Reset", email.subject) # Or match your subject template
        self.assertTrue(len(email.alternatives) > 0) # Check that HTML part exists
        self.assertEqual(email.alternatives[0][1], 'text/html')


class TestAPIUtilityViews(BaseUsersViewTest):
    def test_check_email_availability(self):
        url = reverse('users:check_email')
        # missing email
        resp = self.client.get(url)
        self.assertJSONEqual(resp.content, {'available': False, 'message': 'Email required'})
        # taken
        resp = self.client.get(url, {'email': self.member.email})
        self.assertJSONEqual(resp.content, {'available': False, 'message': 'Email taken'})
        # available
        resp = self.client.get(url, {'email': 'free@example.com'})
        self.assertJSONEqual(resp.content, {'available': True, 'message': 'Email available'})

    def test_check_phone_availability(self):
        url = reverse('users:check_phone')
        # missing
        resp = self.client.get(url)
        self.assertJSONEqual(resp.content, {'available': False, 'message': 'Phone required'})
        # create user with phone
        self.member.phone = '+2348011122233'
        self.member.save(update_fields=['phone'])
        # taken
        resp = self.client.get(url, {'phone': '+2348011122233'})
        self.assertJSONEqual(resp.content, {'available': False, 'message': 'Phone taken'})
        # available
        resp = self.client.get(url, {'phone': '+2348099999999'})
        self.assertJSONEqual(resp.content, {'available': True, 'message': 'Phone available'})

    def test_validate_referral_code(self):
        url = reverse('users:validate_referral')
        # missing
        resp = self.client.get(url)
        self.assertJSONEqual(resp.content, {'valid': False, 'message': 'Code required'})
        # invalid
        resp = self.client.get(url, {'code': 'NOPE'})
        self.assertJSONEqual(resp.content, {'valid': False, 'message': 'Invalid referral code'})
        # valid
        resp = self.client.get(url, {'code': self.ref_code})
        data = resp.json()
        self.assertTrue(data['valid'])
        self.assertIn('referrer', data)
        self.assertEqual(data['referrer']['username'], self.admin.username)


class TestUserProfileViews(BaseUsersViewTest):
    def test_profile_edit_and_extended_form(self):
        c = self.login(self.member)
        url = reverse('users:profile')
        # GET shows extended form & profile
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('extended_profile', resp.context)
        self.assertIn('extended_form', resp.context)

        # POST updates both
        data = {
            'first_name': 'Zed',
            'last_name': 'Zero',
            # ExtendedProfile fields in a separate form; the view builds it from POST
            'bio': 'ignored by user form',  # ensure no crash
            'location': 'Abuja',  # consumed by ExtendedProfileForm
        }
        resp2 = c.post(url, data=data, follow=True)
        self.assertEqual(resp2.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, 'Zed')
        profile = UserProfile.objects.get(user=self.member)
        # Depending on ExtendedProfileForm fields, at least ensure object exists
        self.assertIsNotNone(profile)
        msgs = list(messages.get_messages(resp2.wsgi_request))
        self.assertTrue(any('updated successfully' in m.message.lower() for m in msgs))

    def test_public_profile_view_by_username(self):
        # ensure profile exists
        UserProfile.objects.get_or_create(user=self.member)
        url = reverse('users:public_profile', kwargs={'username': self.member.username})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['profile_user'].pk, self.member.pk)
        self.assertIn('extended_profile', resp.context)
