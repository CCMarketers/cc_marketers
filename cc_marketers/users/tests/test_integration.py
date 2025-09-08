# apps/users/tests/test_integration.py
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from unittest.mock import patch
from decimal import Decimal

from users.models import UserProfile,  PhoneVerificationToken
from referrals.models import ReferralCode, Referral
from wallets.models import Wallet, Transaction
from .test_utils import BaseTestCase

User = get_user_model()


class CompleteUserJourneyTest(BaseTestCase):
    """Test complete user journey from registration to active participation."""
    
    def test_complete_member_journey(self):
        """Test complete member user journey."""
        # Step 1: User visits registration with referral
        referrer = self.create_user(email='referrer@example.com')
        self.create_referral_code(user=referrer, code='MEMBER123')
        
        # Step 2: Registration with referral
        with patch('users.views.send_verification_email') as mock_send:
            mock_send.return_value = True
            response = self.client.post(reverse('users:register'), {
                'email': 'member@example.com',
                'first_name': 'Test',
                'last_name': 'Member',
                'phone': '+2348012345678',
                'password1': 'StrongPassword123!',
                'password2': 'StrongPassword123!',
                'role': User.MEMBER,
                'referral_code': 'MEMBER123'
            })
        
        self.assertRedirects(response, reverse('users:profile_setup'))
        
        # Verify user creation
        member = User.objects.get(email='member@example.com')
        self.assertEqual(member.role, User.MEMBER)
        
        # Verify referral was created
        referral = Referral.objects.get(referred=member)
        self.assertEqual(referral.referrer, referrer)
        
        # Step 3: Profile setup
        response = self.client.post(reverse('users:profile_setup'), {
            'first_name': 'Test',
            'last_name': 'Member',
            'phone': '+2348012345678',
            'bio': 'I am a test member',
            'country': 'Nigeria',
            'state': 'Lagos',
            'city': 'Lagos',
            'receive_email_notifications': True,
            'location': 'Lagos, Nigeria',
            'skills': 'Data Entry, Social Media'
        })
        
        self.assertRedirects(response, reverse('users:dashboard'))
        
        # Verify profile data
        member.refresh_from_db()
        self.assertEqual(member.bio, 'I am a test member')
        self.assertEqual(member.country, 'Nigeria')
        
        profile = UserProfile.objects.get(user=member)
        self.assertEqual(profile.location, 'Lagos, Nigeria')
        self.assertEqual(profile.skills, 'Data Entry, Social Media')
        
        # Step 4: Dashboard access
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Member')
        
        # Step 5: Email verification
        uidb64 = urlsafe_base64_encode(force_bytes(member.pk))
        token = default_token_generator.make_token(member)
        
        response = self.client.get(reverse('users:verify_email', args=[uidb64, token]))
        
        member.refresh_from_db()
        self.assertTrue(member.email_verified)
        
        # Step 6: Phone verification
        response = self.client.post(reverse('users:phone_verify'), {
            'phone': '+2348012345678'
        })
        self.assertRedirects(response, reverse('users:phone_verify_code'))
        
        # Get verification token and verify
        phone_token = PhoneVerificationToken.objects.get(user=member)
        response = self.client.post(reverse('users:phone_verify_code'), {
            'code': phone_token.token
        })
        self.assertRedirects(response, reverse('users:dashboard'))
        
        member.refresh_from_db()
        self.assertTrue(member.phone_verified)
        
        # Step 7: Profile update
        response = self.client.post(reverse('users:profile'), {
            'first_name': 'Updated',
            'last_name': 'Member',
            'phone': '+2348012345678',
            'bio': 'Updated bio',
            'country': 'Nigeria',
            'state': 'Lagos', 
            'city': 'Lagos',
            'receive_email_notifications': True,
            'occupation': 'Virtual Assistant',
            'company': 'Freelance',
            'skills': 'Data Entry, Social Media, Customer Service'
        })
        
        self.assertRedirects(response, reverse('users:profile'))
        
        # Verify updates
        member.refresh_from_db()
        self.assertEqual(member.first_name, 'Updated')
        self.assertEqual(member.bio, 'Updated bio')
        
        profile.refresh_from_db()
        self.assertEqual(profile.occupation, 'Virtual Assistant')
        
        # Step 8: Password change
        response = self.client.post(reverse('users:password_change'), {
            'current_password': 'StrongPassword123!',
            'new_password1': 'NewPassword456!',
            'new_password2': 'NewPassword456!'
        })
        
        self.assertRedirects(response, reverse('users:profile'))
        
        # Verify password changed
        member.refresh_from_db()
        self.assertTrue(member.check_password('NewPassword456!'))
        
        # Final verification: User is fully set up
        self.assertTrue(member.email_verified)
        self.assertTrue(member.phone_verified)
        self.assertTrue(hasattr(member, 'profile'))
        self.assertTrue(Referral.objects.filter(referred=member).exists())
    
    def test_complete_advertiser_journey(self):
        """Test complete advertiser user journey."""
        # Registration as advertiser
        with patch('users.views.send_verification_email') as mock_send:
            mock_send.return_value = True
            response = self.client.post(reverse('users:register'), {
                'email': 'advertiser@example.com',
                'first_name': 'Test',
                'last_name': 'Advertiser',
                'password1': 'StrongPassword123!',
                'password2': 'StrongPassword123!',
                'role': User.ADVERTISER
            })
        
        advertiser = User.objects.get(email='advertiser@example.com')
        self.assertEqual(advertiser.role, User.ADVERTISER)
        self.assertTrue(advertiser.can_post_tasks())
        
        # Profile setup with business info
        response = self.client.post(reverse('users:profile_setup'), {
            'first_name': 'Test',
            'last_name': 'Advertiser',
            'bio': 'Business owner looking for virtual assistance',
            'country': 'Nigeria',
            'receive_email_notifications': True,
            'location': 'Abuja, Nigeria',
            'skills': 'Business Management'
        })
        
        # Dashboard should show advertiser-specific content
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Profile should be set up for business use
        profile = UserProfile.objects.get(user=advertiser)
        self.assertEqual(profile.location, 'Abuja, Nigeria')
    
    def test_admin_user_journey(self):
        """Test admin user journey with special permissions."""
        # Create admin
        admin = self.create_admin_user(email='admin@example.com')
        self.login_user(user=admin)
        
        # Admin should have moderation permissions
        self.assertTrue(admin.can_moderate())
        self.assertTrue(admin.is_staff)
        
        # Dashboard access
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Admin should be able to access all areas
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)


class ReferralSystemIntegrationTest(BaseTestCase):
    """Test referral system integration."""
    
    def test_multi_level_referral_chain(self):
        """Test multi-level referral chain creation."""
        # Level 0: Original referrer
        referrer_l0 = self.create_user(email='referrer0@example.com')
        self.create_referral_code(user=referrer_l0, code='LEVEL0')
        
        # Level 1: First referral
        with patch('users.views.send_verification_email') as mock_send:
            mock_send.return_value = True
            self.client.post(reverse('users:register'), {
                'email': 'referred1@example.com',
                'first_name': 'Level1',
                'last_name': 'User',
                'password1': 'StrongPassword123!',
                'password2': 'StrongPassword123!',
                'role': User.MEMBER,
                'referral_code': 'LEVEL0'
            })
        
        referred_l1 = User.objects.get(email='referred1@example.com')
        referral_l1 = Referral.objects.get(referred=referred_l1)
        self.assertEqual(referral_l1.referrer, referrer_l0)
        self.assertEqual(referral_l1.level, 1)
        
        # Level 2: Second level referral
        self.client.logout()
        self.create_referral_code(user=referred_l1, code='LEVEL1')
        
        with patch('users.views.send_verification_email') as mock_send:
            mock_send.return_value = True
            self.client.post(reverse('users:register'), {
                'email': 'referred2@example.com',
                'first_name': 'Level2',
                'last_name': 'User',
                'password1': 'StrongPassword123!',
                'password2': 'StrongPassword123!',
                'role': User.MEMBER,
                'referral_code': 'LEVEL1'
            })
        
        referred_l2 = User.objects.get(email='referred2@example.com')
        referral_l2 = Referral.objects.get(referred=referred_l2)
        self.assertEqual(referral_l2.referrer, referred_l1)
        
        # Verify chain exists
        self.assertEqual(Referral.objects.count(), 2)
    
    def test_referral_with_invalid_codes(self):
        """Test referral system handles invalid codes gracefully."""
        # Try registration with invalid referral code
        response = self.client.post(reverse('users:register'), {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'StrongPassword123!',
            'password2': 'StrongPassword123!',
            'role': User.MEMBER,
            'referral_code': 'INVALID123'
        })
        
        # Should show form errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid referral code')
        
        # User should not be created
        self.assertFalse(User.objects.filter(email='test@example.com').exists())
    
    def test_referral_code_generation_and_usage(self):
        """Test referral code generation and usage flow."""
        # Create user
        user = self.create_user()
        self.login_user(user=user)
        
        # Access dashboard to trigger referral code creation
        response = self.client.get(reverse('users:dashboard'))
        
        # Referral code should be created
        referral_code = ReferralCode.objects.get(user=user)
        self.assertTrue(referral_code.is_active)
        
        # Referral link should be in context
        self.assertIn('referral_link', response.context)
        referral_link = response.context['referral_link']
        self.assertIn(referral_code.code, referral_link)


class VerificationSystemIntegrationTest(BaseTestCase):
    """Test verification system integration."""
    
    def test_complete_verification_flow(self):
        """Test complete email and phone verification flow."""
        # Create unverified user
        user = self.create_user(email='verify@example.com')
        self.assertFalse(user.email_verified)
        self.assertFalse(user.phone_verified)
        
        self.login_user(user=user)
        
        # Resend email verification
        with patch('users.views.send_verification_email') as mock_send:
            mock_send.return_value = True
            response = self.client.post(reverse('users:resend_verification'))
            self.assertRedirects(response, reverse('users:dashboard'))
        
        # Verify email
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        
        response = self.client.get(reverse('users:verify_email', args=[uidb64, token]))
        
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        
        # Phone verification request
        response = self.client.post(reverse('users:phone_verify'), {
            'phone': '+2348012345678'
        })
        
        user.refresh_from_db()
        self.assertEqual(user.phone, '+2348012345678')
        
        # Phone verification confirmation
        phone_token = PhoneVerificationToken.objects.get(user=user)
        response = self.client.post(reverse('users:phone_verify_code'), {
            'code': phone_token.token
        })
        
        user.refresh_from_db()
        self.assertTrue(user.phone_verified)
        
        # Both verifications should be complete
        self.assertTrue(user.email_verified)
        self.assertTrue(user.phone_verified)
    
    def test_verification_edge_cases(self):
        """Test verification system edge cases."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Try to verify with expired token
        from django.utils import timezone
        from datetime import timedelta
        
        phone_token = PhoneVerificationToken.objects.create(
            user=user,
            token='123456'
        )
        phone_token.expires_at = timezone.now() - timedelta(minutes=1)
        phone_token.save()
        
        response = self.client.post(reverse('users:phone_verify_code'), {
            'code': '123456'
        })
        
        self.assertEqual(response.status_code, 200)  # Form errors
        self.assertContains(response, 'expired')
        
        # Try to verify already verified user
        user.email_verified = True
        user.save()
        
        response = self.client.post(reverse('users:resend_verification'))
        self.assert_message_sent(response, 'already verified')


class AuthenticationIntegrationTest(BaseTestCase):
    """Test authentication system integration."""
    
    def test_multi_method_authentication(self):
        """Test authentication with email and phone."""
        # Create user with phone
        self.create_user(
            email='auth@example.com',
            phone='+2348012345678'
        )
        
        # Test email authentication
        response = self.client.post(reverse('users:login'), {
            'username': 'auth@example.com',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)  # Successful login
        
        self.client.logout()
        
        # Test phone authentication
        response = self.client.post(reverse('users:login'), {
            'username': '+2348012345678',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)  # Successful login
    
    def test_authentication_with_role_based_redirect(self):
        """Test role-based redirects after authentication."""
        # Test member redirect
        member = self.create_user(role=User.MEMBER)
        response = self.client.post(reverse('users:login'), {
            'username': member.email,
            'password': 'testpass123'
        })
        self.assertRedirects(response, reverse('tasks:task_list'))
        
        # Test advertiser redirect
        self.client.logout()
        advertiser = self.create_user(role=User.ADVERTISER, email='adv@example.com')
        response = self.client.post(reverse('users:login'), {
            'username': advertiser.email,
            'password': 'testpass123'
        })
        self.assertRedirects(response, reverse('tasks:my_tasks'))
        
        # Test admin redirect
        self.client.logout()
        admin = self.create_admin_user()
        response = self.client.post(reverse('users:login'), {
            'username': admin.email,
            'password': 'testpass123'
        })
        self.assertRedirects(response, reverse('users:dashboard'))


class ProfileIntegrationTest(BaseTestCase):
    """Test profile system integration."""
    
    def test_profile_creation_and_updates(self):
        """Test profile creation and update flow."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Profile should exist automatically
        self.assertTrue(hasattr(user, 'profile'))
        
        # Update basic profile
        response = self.client.post(reverse('users:profile'), {
            'first_name': 'Updated',
            'last_name': 'Name',
            'bio': 'Updated bio',
            'country': 'Nigeria',
            'receive_email_notifications': True,
            # Extended profile
            'occupation': 'Developer',
            'skills': 'Python, Django'
        })
        
        self.assertRedirects(response, reverse('users:profile'))
        
        # Verify updates
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Updated')
        self.assertEqual(user.bio, 'Updated bio')
        
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.occupation, 'Developer')
        self.assertEqual(profile.skills, 'Python, Django')
    
    def test_public_profile_accessibility(self):
        """Test public profile accessibility and content."""
        user = self.create_user()
        self.create_user_profile(
            user=user,
            occupation='Software Developer',
            skills='Python, Django, React'
        )
        
        # Public profile should be accessible without authentication
        response = self.client.get(
            reverse('users:public_profile', args=[user.username])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, user.get_display_name())
        self.assertContains(response, 'Software Developer')


class PasswordManagementIntegrationTest(BaseTestCase):
    """Test password management integration."""
    
    def test_password_change_flow(self):
        """Test password change flow."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Change password
        response = self.client.post(reverse('users:password_change'), {
            'current_password': 'testpass123',
            'new_password1': 'newpassword456',
            'new_password2': 'newpassword456'
        })
        
        self.assertRedirects(response, reverse('users:profile'))
        
        # Verify password changed
        user.refresh_from_db()
        self.assertTrue(user.check_password('newpassword456'))
        
        # Should still be logged in
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_password_reset_flow(self):
        """Test password reset flow."""
        user = self.create_user()
        
        # Request password reset
        response = self.client.post(reverse('users:password_reset'), {
            'email': user.email
        })
        
        self.assertRedirects(response, reverse('users:password_reset_done'))
        
        # Should handle both existing and non-existing emails gracefully
        response = self.client.post(reverse('users:password_reset'), {
            'email': 'nonexistent@example.com'
        })
        
        self.assertRedirects(response, reverse('users:password_reset_done'))


class APIIntegrationTest(BaseTestCase):
    """Test API endpoint integration."""
    
    def test_availability_check_apis(self):
        """Test email and phone availability APIs."""
        self.create_user(
            email='existing@example.com',
            phone='+2348012345678'
        )
        
        # Check existing email
        response = self.client.get(
            reverse('users:check_email') + '?email=existing@example.com'
        )
        data = response.json()
        self.assertFalse(data['available'])
        
        # Check available email
        response = self.client.get(
            reverse('users:check_email') + '?email=available@example.com'
        )
        data = response.json()
        self.assertTrue(data['available'])
        
        # Check existing phone
        response = self.client.get(
            reverse('users:check_phone') + '?phone=%2B2348012345678'
        )
        data = response.json()
        self.assertFalse(data['available'])
        
        # Check available phone
        response = self.client.get(
            reverse('users:check_phone') + '?phone=%2B2348099999999'
        )
        data = response.json()
        self.assertTrue(data['available'])
    
    def test_referral_validation_api(self):
        """Test referral code validation API."""
        referrer = self.create_user()
        self.create_referral_code(user=referrer, code='VALID123')
        
        # Valid referral code
        response = self.client.get(
            reverse('users:validate_referral') + '?code=VALID123'
        )
        data = response.json()
        self.assertTrue(data['valid'])
        self.assertIn('referrer', data)
        
        # Invalid referral code
        response = self.client.get(
            reverse('users:validate_referral') + '?code=INVALID123'
        )
        data = response.json()
        self.assertFalse(data['valid'])


class CrossAppIntegrationTest(TransactionTestCase):
    """Test integration with other apps (wallets, tasks, referrals)."""
    
    def test_user_wallet_integration(self):
        """Test user wallet integration."""
        user = self.create_user()
        
        # Wallet should be created for user
        from wallets.services import WalletService
        wallet = WalletService.get_or_create_wallet(user)
        
        self.assertEqual(wallet.user, user)
        self.assertEqual(wallet.balance, Decimal('0.00'))
    
    def test_user_dashboard_cross_app_data(self):
        """Test dashboard displays data from multiple apps."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Create some cross-app data
        Wallet.objects.create(user=user, balance=Decimal('100.00'))
        Transaction.objects.create(
            user=user,
            amount=Decimal('50.00'),
            transaction_type='credit',
            description='Test transaction'
        )
        
        response = self.client.get(reverse('users:dashboard'))
        context = response.context
        
        # Should include wallet and transaction data
        self.assertIn('recent_transactions', context)
        self.assertIn('available_balance', context)
    
    def test_referral_across_apps(self):
        """Test referral system works across different app interactions."""
        referrer = self.create_user()
        referral_code = self.create_referral_code(user=referrer)
        
        # Register new user with referral
        with patch('users.views.send_verification_email') as mock_send:
            mock_send.return_value = True
            self.client.post(reverse('users:register'), {
                'email': 'referred@example.com',
                'first_name': 'Referred',
                'last_name': 'User',
                'password1': 'StrongPassword123!',
                'password2': 'StrongPassword123!',
                'role': User.MEMBER,
                'referral_code': referral_code.code
            })
        
        referred = User.objects.get(email='referred@example.com')
        
        # Referral should exist
        referral = Referral.objects.get(referred=referred)
        self.assertEqual(referral.referrer, referrer)
        
        # Both users should have proper setup across apps
        self.assertTrue(hasattr(referrer, 'profile'))
        self.assertTrue(hasattr(referred, 'profile'))


class ErrorHandlingIntegrationTest(BaseTestCase):
    """Test error handling across integrated flows."""
    
    def test_registration_with_service_failures(self):
        """Test registration handles service failures gracefully."""
        # Test with email service failure
        with patch('users.views.send_verification_email') as mock_send:
            mock_send.return_value = False  # Email sending fails
            
            response = self.client.post(reverse('users:register'), {
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'User',
                'password1': 'StrongPassword123!',
                'password2': 'StrongPassword123!',
                'role': User.MEMBER
            })
            
            # User should still be created and logged in
            self.assertRedirects(response, reverse('users:profile_setup'))
            self.assertTrue(User.objects.filter(email='test@example.com').exists())
    
    def test_verification_with_edge_cases(self):
        """Test verification handles edge cases."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Test phone verification with invalid phone format
        response = self.client.post(reverse('users:phone_verify'), {
            'phone': 'invalid-phone'
        })
        
        # Should handle gracefully and show form errors
        self.assertEqual(response.status_code, 200)
        
        # Test verification code with malformed input
        response = self.client.post(reverse('users:phone_verify_code'), {
            'code': 'abc123'  # Non-numeric
        })
        
        self.assertEqual(response.status_code, 200)
    
    def test_dashboard_with_missing_data(self):
        """Test dashboard handles missing cross-app data."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Dashboard should work even without wallet/task data
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should have default values for missing data
        context = response.context
        self.assertIn('user_stats', context)
        self.assertIn('recent_transactions', context)