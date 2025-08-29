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
    """Send email verification to user"""
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
        logger.debug(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        logger.debug(f"EMAIL_HOST: {settings.EMAIL_HOST}")
        logger.debug(f"EMAIL_PORT: {settings.EMAIL_PORT}")
        logger.debug(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
        logger.debug(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

    except Exception as e:
        logger.error(f"Failed to send verification email to {user.email}: {str(e)}")


# def send_password_reset_email(user):
#     """Send password reset email to user"""
#     try:
#         token = default_token_generator.make_token(user)
#         uid = urlsafe_base64_encode(force_bytes(user.pk))
        
#         subject = 'Password Reset'
#         message = render_to_string('email/password_reset.html', {
#             'user': user,
#             'uid': uid,
#             'token': token,
#             'domain': settings.FRONTEND_URL,
#         })
        
#         send_mail(
#             subject,
#             message,
#             settings.DEFAULT_FROM_EMAIL,
#             [user.email],
#             html_message=message
#         )

#         logger.info(f"✅ Password reset email sent to {user.email}")
#     except Exception as e:
#         logger.error(f"Failed to send password reset email: {str(e)}", exc_info=True)


