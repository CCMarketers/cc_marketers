from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from .models import User, UserProfile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Create or update UserProfile when User is created or saved.
    This combines profile creation & saving into one handler.
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Update only if profile exists to avoid redundant queries
        if hasattr(instance, "profile"):
            instance.profile.save()


@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    """Handle user login (extend with logging/analytics if needed)."""
    pass


@receiver(user_logged_out)
def user_logged_out_handler(sender, request, user, **kwargs):
    """Handle user logout (extend with custom logic if needed)."""
    pass


# Example (Optional): Auto-create wallet for new users
# @receiver(post_save, sender=User)
# def create_user_wallet(sender, instance, created, **kwargs):
#     if created:
#         from wallets.models import Wallet
#         Wallet.objects.create(user=instance)
