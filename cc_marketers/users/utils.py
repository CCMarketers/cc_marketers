from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from redis_service import app_cache # Import Redis caching
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def send_verification_email(user):
    """Send email verification to user, with caching to prevent spam"""
    cache_key = f"email:verification:{user.id}"
    if app_cache.redis.exists(cache_key):
        logger.info(f"⏳ Skipping verification email to {user.email} (cached recently)")
        return

    try:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        subject = 'Verify your email address'
        message = render_to_string('email/verification_email.html', {
            'user': user,
            'uid': uid,
            'token': token,
            'domain': settings.BACKEND_URL,
        })
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=message
        )

       # Cache for 5 minutes to prevent re-sending too quickly
        app_cache.redis.set(cache_key, True, timeout=300)

        logger.info(f"✅ Verification email sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")


def send_password_reset_email(user):
    """Send password reset email to user, with caching to prevent spam"""
    cache_key = f"email:password_reset:{user.id}"
    if app_cache.redis.exists(cache_key):
        logger.info(f"⏳ Skipping password reset email to {user.email} (cached recently)")
        return

    try:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        subject = 'Password Reset'
        message = render_to_string('email/password_reset.html', {
            'user': user,
            'uid': uid,
            'token': token,
            'domain': settings.FRONTEND_URL,
        })
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=message
        )

       # Cache for 5 minutes to prevent re-sending too quickly
        app_cache.redis.set(cache_key, True, timeout=300)

        logger.info(f"✅ Password reset email sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send password reset email: {str(e)}", exc_info=True)



# def send_verification_email(user):
#     send_verification_email_task.delay(user.id)

# def send_password_reset_email(user):
#     send_password_reset_email_task.delay(user.id)
