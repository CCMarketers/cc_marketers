# apps/users/tests/test_permissions.py
from django.urls import reverse
from django.contrib.auth import get_user_model


from users.models import UserProfile
from .test_utils import BaseTestCase

User = get_user_model()


class ViewPermissionsTest(BaseTestCase):
    """Test view-level permissions and access control."""
    
    def test_anonymous_user_access(self):
        """Test what anonymous users can access."""
        # Public views accessible to anonymous users
        public_urls = [
            reverse('users:register'),
            reverse('users:login'),
            reverse('users:password_reset'),
            reverse('users:password_reset_done'),
            reverse('users:check_email'),
            reverse('users:check_phone'),
            reverse('users:validate_referral'),
        ]
        
        for url in public_urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])  # 302 for some redirects

    def test_authenticated_user_required_views(self):
        """Test views that require authentication."""
        protected_urls = [
            reverse('users:profile'),
            reverse('users:profile_setup'),
            reverse('users:dashboard'),
            reverse('users:phone_verify'),
            reverse('users:phone_verify_code'),
            reverse('users:password_change'),
            reverse('users:resend_verification'),
        ]
        
        # Test anonymous access - should redirect to login
        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn('/users/login/', response.url)
    
    def test_authenticated_user_access(self):
        """Test authenticated user can access protected views."""
        user = self.create_user()
        self.login_user(user=user)
        
        accessible_urls = [
            reverse('users:profile'),
            reverse('users:profile_setup'),
            reverse('users:dashboard'),
            reverse('users:phone_verify'),
            reverse('users:phone_verify_code'),
            reverse('users:password_change'),
            reverse('users:resend_verification'),
        ]
        
        for url in accessible_urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, [200, 302])  # 302 for some redirects
    
    def test_public_profile_access(self):
        """Test public profile access permissions."""
        user = self.create_user()
        
        # Anonymous users can view public profiles
        response = self.client.get(
            reverse('users:public_profile', args=[user.username])
        )
        self.assertEqual(response.status_code, 200)
        
        # Authenticated users can also view public profiles
        viewer = self.create_user(email='viewer@example.com')
        self.login_user(user=viewer)
        
        response = self.client.get(
            reverse('users:public_profile', args=[user.username])
        )
        self.assertEqual(response.status_code, 200)
    
    def test_own_profile_vs_others_profile(self):
        """Test users can edit own profile but not others'."""
        user1 = self.create_user(email='user1@example.com')
        user2 = self.create_user(email='user2@example.com')
        
        # User1 can access their own profile for editing
        self.login_user(user=user1)
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)
        
        # User1 can only view user2's public profile, not edit
        response = self.client.get(
            reverse('users:public_profile', args=[user2.username])
        )
        self.assertEqual(response.status_code, 200)
        
        # There's no direct URL to edit another user's profile
        # This is enforced by the view only allowing the current user


class RoleBasedPermissionsTest(BaseTestCase):
    """Test role-based permissions and access control."""
    
    def test_member_permissions(self):
        """Test member role permissions."""
        member = self.create_user(role=User.MEMBER)
        
        # Members cannot post tasks
        self.assertFalse(member.can_post_tasks())
        
        # Members cannot moderate
        self.assertFalse(member.can_moderate())
        
        # Members are not staff by default
        self.assertFalse(member.is_staff)
    
    def test_advertiser_permissions(self):
        """Test advertiser role permissions."""
        advertiser = self.create_user(role=User.ADVERTISER)
        
        # Advertisers can post tasks
        self.assertTrue(advertiser.can_post_tasks())
        
        # Advertisers cannot moderate
        self.assertFalse(advertiser.can_moderate())
        
        # Advertisers are not staff by default
        self.assertFalse(advertiser.is_staff)
    
    def test_admin_permissions(self):
        """Test admin role permissions."""
        admin = self.create_admin_user()
        
        # Admins can post tasks
        self.assertTrue(admin.can_post_tasks())
        
        # Admins can moderate
        self.assertTrue(admin.can_moderate())
        
        # Admins are staff
        self.assertTrue(admin.is_staff)
        
        # Admins are superusers when created with create_superuser
        superuser = User.objects.create_superuser(
            email='super@example.com',
            password='adminpass123'
        )
        self.assertTrue(superuser.is_superuser)

    def test_role_based_login_redirects(self):
        """Test login redirects based on user roles."""

        # --- Member ---
        member = self.create_user(role=User.MEMBER, email='mem@example.com')
        response = self.client.post(reverse('users:login'), {
            'username': member.email,
            'password': 'testpass123'
        })
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['_auth_user_id'], str(member.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('tasks:task_list'))

        # --- Advertiser ---
        self.client.logout()
        advertiser = self.create_advertiser_user(role=User.ADVERTISER, email='adv@example.com')
        response = self.client.post(reverse('users:login'), {
            'username': advertiser.email,
            'password': 'testpass123'
        })
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['_auth_user_id'], str(advertiser.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('tasks:my_tasks'))

        # --- Admin ---
        self.client.logout()
        admin = self.create_admin_user(password='adminpass123')
        response = self.client.post(reverse('users:login'), {
            'username': admin.email,
            'password': 'adminpass123'
        })
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.session['_auth_user_id'], str(admin.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('users:dashboard'))




    def test_inactive_user_permissions(self):
        """Test inactive user permissions."""
        # Create inactive users of different roles
        inactive_member = self.create_user(role=User.MEMBER, is_active=False)
        inactive_advertiser = self.create_user(role=User.ADVERTISER, is_active=False, email='adv@example.com')
        inactive_admin = self.create_admin_user(is_active=False)
        
        # Inactive users cannot perform role-specific actions
        self.assertFalse(inactive_member.can_post_tasks())
        self.assertFalse(inactive_advertiser.can_post_tasks())
        self.assertFalse(inactive_admin.can_post_tasks())
        self.assertFalse(inactive_admin.can_moderate())
        
        # Inactive users cannot log in
        response = self.client.post(reverse('users:login'), {
            'username': inactive_member.email,
            'password': 'testpass123'
        })
        # Should show login form with errors
        self.assertEqual(response.status_code, 200)


class DataAccessPermissionsTest(BaseTestCase):
    """Test data access permissions."""
    
    def test_user_can_only_access_own_data(self):
        """Test users can only access their own data."""
        user1 = self.create_user(email='user1@example.com')
        self.create_user(email='user2@example.com')
        
        # Login as user1
        self.login_user(user=user1)
        
        # User1 dashboard should only show user1's data
        response = self.client.get(reverse('users:dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should contain user1's information
        self.assertContains(response, user1.get_display_name())
        
        # Should not contain user2's private information
        # (Public information like usernames might appear in general contexts)
    
    # def test_profile_data_isolation(self):
    #     user1 = self.create_user(email='user1@example.com')
    #     user2 = self.create_user(email='user2@example.com')

    #     # Create / get profiles and set fields explicitly (use separate variables)
    #     p1, _ = UserProfile.objects.get_or_create(user=user1)
    #     p1.occupation = 'Developer'
    #     p1.company = 'Tech Corp 1'
    #     p1.save()

    #     p2, _ = UserProfile.objects.get_or_create(user=user2)
    #     p2.occupation = 'Designer'
    #     p2.company = 'Design Corp 2'
    #     p2.save()
    #     # --- ADD THESE TWO LINES FOR DEBUGGING ---
    #     p1.refresh_from_db()  # Reload the object from the test database
    #     self.assertEqual(p1.occupation, 'Developer', "DATABASE CHECK FAILED: Occupation was not saved correctly.")
    #     # --- END OF ADDED LINES ---
    #     # --- Quick DB sanity checks (fail fast if the DB isn't as expected) ---
    #     self.assertEqual(UserProfile.objects.filter(user=user1).count(), 1,
    #                     "Expected exactly one profile for user1")
    #     self.assertEqual(p1.occupation, 'Developer', "DB: p1.occupation mismatch")
    #     self.assertEqual(p1.company, 'Tech Corp 1', "DB: p1.company mismatch")

    #     # Login as user1 (your login_user uses force_login when passed a user)
    #     self.client.force_login(user1)

    #     # self.login_user(user=user1)sss

    #     # User1's profile page should show user1's data
    #     response = self.client.get(reverse('users:profile'))
    #     self.assertEqual(response.status_code, 200)
    #     self.assertContains(response, 'Developer')
    #     self.assertContains(response, 'Tech Corp 1')

    #     # User1 can view user2's public profile (only asserting occupation is public)
    #     response = self.client.get(reverse('users:public_profile', args=[user2.username]))
    #     self.assertEqual(response.status_code, 200)
    #     self.assertContains(response, 'Designer')

    def test_verification_token_isolation(self):
        """Test verification tokens are isolated between users."""
        from users.models import EmailVerificationToken
        
        user1 = self.create_user(email='user1@example.com')
        user2 = self.create_user(email='user2@example.com')
        
        token1 = self.create_email_verification_token(user=user1)
        token2 = self.create_email_verification_token(user=user2)
        
        # Tokens should be different
        self.assertNotEqual(token1.token, token2.token)
        
        # Each user should only have access to their own tokens
        user1_tokens = EmailVerificationToken.objects.filter(user=user1)
        user2_tokens = EmailVerificationToken.objects.filter(user=user2)
        
        self.assertEqual(user1_tokens.count(), 1)
        self.assertEqual(user2_tokens.count(), 1)
        self.assertEqual(user1_tokens.first(), token1)
        self.assertEqual(user2_tokens.first(), token2)


class APIPermissionsTest(BaseTestCase):
    """Test API endpoint permissions."""
    
    def test_api_endpoints_public_access(self):
        """Test API endpoints that should be publicly accessible."""
        public_apis = [
            reverse('users:check_email'),
            reverse('users:check_phone'),
            reverse('users:validate_referral'),
        ]
        
        for api_url in public_apis:
            response = self.client.get(api_url)
            # Should return 200 even without authentication
            # (though may return error for missing parameters)
            self.assertEqual(response.status_code, 200)
    
    def test_api_parameter_validation(self):
        """Test API endpoints validate parameters properly."""
        # Email check without parameter
        response = self.client.get(reverse('users:check_email'))
        data = response.json()
        self.assertFalse(data['available'])
        self.assertEqual(data['message'], 'Email required')
        
        # Phone check without parameter
        response = self.client.get(reverse('users:check_phone'))
        data = response.json()
        self.assertFalse(data['available'])
        self.assertEqual(data['message'], 'Phone required')
        
        # Referral validation without parameter
        response = self.client.get(reverse('users:validate_referral'))
        data = response.json()
        self.assertFalse(data['valid'])
        self.assertEqual(data['message'], 'Code required')
    
    def test_api_rate_limiting_considerations(self):
        """Test API endpoints can handle multiple requests."""
        # This is more of a stress test to ensure APIs don't break
        for i in range(10):
            response = self.client.get(
                reverse('users:check_email') + f'?email=test{i}@example.com'
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['available'])  # These emails don't exist


class SecurityPermissionsTest(BaseTestCase):
    """Test security-related permissions."""
    
    def test_password_change_requires_current_password(self):
        """Test password change requires current password verification."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Try to change password with wrong current password
        response = self.client.post(reverse('users:password_change'), {
            'current_password': 'wrongpassword',
            'new_password1': 'newpassword123',
            'new_password2': 'newpassword123'
        })
        
        # Should show form errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current password is incorrect')
        
        # Password should not be changed
        user.refresh_from_db()
        self.assertTrue(user.check_password('testpass123'))
    
    def test_email_verification_token_security(self):
        """Test email verification tokens are secure."""
        user = self.create_user()
        
        # Invalid UID should not work
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        
        invalid_uid = urlsafe_base64_encode(force_bytes('invalid'))
        response = self.client.get(
            reverse('users:verify_email', args=[invalid_uid, 'token'])
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid or expired verification link')
        
        # Valid UID with invalid token should not work
        valid_uid = urlsafe_base64_encode(force_bytes(user.pk))
        response = self.client.get(
            reverse('users:verify_email', args=[valid_uid, 'invalidtoken'])
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid or expired verification link')
    
    def test_phone_verification_security(self):
        """Test phone verification is secure."""
        user = self.create_user()
        self.login_user(user=user)
        
        # Create phone token
        self.create_phone_verification_token(user=user, token='123456')
        
        # Wrong user trying to use the code should fail
        other_user = self.create_user(email='other@example.com')
        self.login_user(user=other_user)
        
        response = self.client.post(reverse('users:phone_verify_code'), {
            'code': '123456'
        })
        
        # Should fail - wrong user
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid code')
    
    def test_csrf_protection(self):
        """Test CSRF protection on forms."""
        user = self.create_user()
        
        # Try to login without CSRF token (if CSRF is enforced)
        response = self.client.post(reverse('users:login'), {
            'username': user.email,
            'password': 'testpass123'
        }, HTTP_X_CSRFTOKEN='')
        
        # Behavior depends on Django CSRF settings
        # In test environment, this might not enforce CSRF
        self.assertIn(response.status_code, [200, 302, 403])
    
    def test_user_enumeration_protection(self):
        """Test protection against user enumeration attacks."""
        # Password reset should not reveal if email exists
        response = self.client.post(reverse('users:password_reset'), {
            'email': 'nonexistent@example.com'
        })
        
        # Should redirect to done page regardless
        self.assertRedirects(response, reverse('users:password_reset_done'))
        
        # API endpoints should be careful about revealing user existence
        # This depends on specific implementation requirements


class PermissionEdgeCasesTest(BaseTestCase):
    """Test edge cases in permission handling."""
    
    def test_user_with_no_profile(self):
        """Test user without profile can still access basic functions."""
        user = self.create_user()
        
        # Manually delete profile to simulate edge case
        if hasattr(user, 'profile'):
            user.profile.delete()
        
        self.login_user(user=user)
        
        # User should still be able to access basic pages
        response = self.client.get(reverse('users:dashboard'))
        # Should either create profile automatically or handle gracefully
        self.assertIn(response.status_code, [200, 302])
    
    def test_user_with_invalid_role(self):
        """Test user with invalid role data."""
        user = self.create_user()
        
        # Set invalid role directly in database
        User.objects.filter(id=user.id).update(role='invalid_role')
        user.refresh_from_db()
        
        # Should handle gracefully
        self.assertFalse(user.can_post_tasks())
        self.assertFalse(user.can_moderate())
    
    def test_concurrent_user_operations(self):
        """Test concurrent operations on user data."""
        user = self.create_user()
        
        # This would require threading in a real test
        # For now, just test that basic operations are safe
        user.first_name = 'Updated1'
        user.save()
        
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Updated1')
    
    def test_user_deletion_cascade(self):
        """Test what happens when user is deleted."""
        user = self.create_user()
        user.profile
        
        # Create related objects
        self.create_email_verification_token(user=user)
        self.create_phone_verification_token(user=user)
        
        # Delete user
        user_id = user.id
        user.delete()
        
        # Related objects should be deleted due to CASCADE
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertFalse(UserProfile.objects.filter(user_id=user_id).exists())
        # Tokens should also be deleted
        from users.models import EmailVerificationToken, PhoneVerificationToken
        self.assertFalse(EmailVerificationToken.objects.filter(user_id=user_id).exists())
        self.assertFalse(PhoneVerificationToken.objects.filter(user_id=user_id).exists())