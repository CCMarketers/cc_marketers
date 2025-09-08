from datetime import timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import User, UserProfile
from django.utils import timezone

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Create or update UserProfile when User is created or saved.
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Ensure we have a profile and update it
        try:
            profile = instance.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=instance)
        
        # Only update if something actually changed to avoid unnecessary saves
        if not profile.updated_at or profile.updated_at < timezone.now() - timedelta(seconds=1):
            profile.updated_at = timezone.now()
            profile.save()


@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    """Handle user login (extend with logging/analytics if needed)."""
    pass


@receiver(user_logged_out)
def user_logged_out_handler(sender, request, user, **kwargs):
    """Handle user logout (extend with custom logic if needed)."""
    pass




