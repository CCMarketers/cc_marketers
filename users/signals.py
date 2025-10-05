from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.utils import timezone
from .models import User, UserProfile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create or update the UserProfile when a User is created or saved.
    """
    if created:
        # Only create a profile for newly created users
        UserProfile.objects.create(user=instance)
    else:
        # If the profile does not exist (edge cases), create it
        profile, _ = UserProfile.objects.get_or_create(user=instance)

        # Update timestamp only if stale (prevents unnecessary saves/signals)
        now = timezone.now()
        if not profile.updated_at or profile.updated_at < now - timedelta(seconds=1):
            profile.updated_at = now
            profile.save(update_fields=["updated_at"])  # save only updated_at


@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    """
    Handle user login (extend with logging/analytics if needed).
    Example: mark last_login_ip or push to analytics.
    """
    # Example:
    # user.profile.last_login_ip = get_client_ip(request)
    # user.profile.save(update_fields=["last_login_ip"])
    pass


@receiver(user_logged_out)
def user_logged_out_handler(sender, request, user, **kwargs):
    """
    Handle user logout (extend with custom logic if needed).
    Example: mark last_logout time.
    """
    # Example:
    # user.profile.last_logout = timezone.now()
    # user.profile.save(update_fields=["last_logout"])
    pass
