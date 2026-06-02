from django.core.mail import send_mail
from django.conf import settings 
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
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

        logger.info(f"✅ Verification email sent to {user.email}")
        return True  # ← was missing

    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")
        return False  # ← was missing


def send_password_reset_email(user):
    try:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        subject = 'Reset your password'
        message = render_to_string('email/password_reset.html', {
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

        logger.info(f"✅ Password reset email sent to {user.email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send password reset email: {str(e)}", exc_info=True)
        return False


