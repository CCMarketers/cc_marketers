
# wallets/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .services import WalletService

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """Automatically create a wallet when a new user is created"""
    if created:
        WalletService.get_or_create_wallet(instance)