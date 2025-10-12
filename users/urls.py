
# apps/users/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from django.urls import reverse_lazy
app_name = 'users'

urlpatterns = [

    path("", views.landing_page, name="landing"),
    path("help/", views.help_center, name="help"),
    path("contact/", views.contact, name="contact"),
    path("terms-of-service/", views.terms, name="terms"),
    path("privacy-policy/", views.privacy, name="privacy"),
    # Authentication
    # Authentication
    # Authentication
    path('register/', views.UserRegistrationView.as_view(), name='register'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.UserLogoutView.as_view(), name='logout'),
    
    # Profile Management
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('profile/setup/', views.ProfileSetupView.as_view(), name='profile_setup'),
    path('dashboard/', views.UserDashboardView.as_view(), name='dashboard'),
    path('profile/<str:username>/', views.PublicProfileView.as_view(), name='public_profile'),
    
    # Email Verification
    path('verify-email/<uidb64>/<token>/', views.EmailVerificationView.as_view(), name='verify_email'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend_verification'),
    
    # Phone Verification
    path('verify-phone/', views.PhoneVerificationView.as_view(), name='phone_verify'),
    path('verify-phone/code/', views.PhoneVerificationCodeView.as_view(), name='phone_verify_code'),
    
    # Password Management
    path('password/change/', views.PasswordChangeView.as_view(), name='password_change'), 
    path(
    'password/reset/',
    views.CustomPasswordResetView.as_view(
        template_name='users/password_reset.html',
        email_template_name='users/password_reset_email.txt',
        html_email_template_name='users/password_reset_email.html',
        subject_template_name='users/password_reset_subject.txt',
        success_url=reverse_lazy('users:password_reset_done'),
    ),
    name='password_reset'),

    path('password/reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='users/password_reset_done.html'
    ), name='password_reset_done'),
    path('password/reset/confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='users/password_reset_confirm.html',
        success_url=reverse_lazy('users:password_reset_complete'),  # 👈 fix

    ), name='password_reset_confirm'),
    path('password/reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='users/password_reset_complete.html'
    ), name='password_reset_complete'),
    
   
    
    # AJAX API endpoints
    path('api/check-email/', views.CheckEmailAvailabilityView.as_view(), name='check_email'),
    path('api/check-phone/', views.CheckPhoneAvailabilityView.as_view(), name='check_phone'),
    path('api/validate-referral/', views.ValidateReferralCodeView.as_view(), name='validate_referral'),
]