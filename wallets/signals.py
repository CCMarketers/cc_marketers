# wallets/signals.py
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Wallet
from . import services

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    """
    Automatically create a wallet for every newly created user.
    If WalletService is available, use it; otherwise fallback to direct model creation.
    """
    if not created or instance is None:
        return

    try:
        # Prefer the service layer if available
        if (
            hasattr(services, "WalletService")
            and hasattr(services.WalletService, "get_or_create_wallet")
        ):
            services.WalletService.get_or_create_wallet(instance)
            return

        # Fallback to direct model creation
        Wallet.objects.get_or_create(user=instance, defaults={"balance": 0})
        logger.info("Wallet created for user %s (fallback)", instance.pk)

    except IntegrityError as ie:
        logger.warning("IntegrityError creating wallet for user %s: %s", instance.pk, ie)
    except Exception as exc:
        logger.exception("Unexpected error creating wallet for user %s: %s", instance.pk, exc)
