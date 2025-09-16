# wallets/signals.py
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.dispatch import receiver
from django.db.models.signals import post_save
import logging

from .models import Wallet
from . import services

logger = logging.getLogger(__name__)
User = get_user_model()

@receiver(post_save, sender=User)
def create_user_wallet(sender, instance, created, **kwargs):
    try:
        if not created or instance is None:
            return

        # Skip redundant database existence check here

        try:
            if hasattr(services, "WalletService") and hasattr(services.WalletService, "get_or_create_wallet"):
                services.WalletService.get_or_create_wallet(instance)
                return
        except Exception as e:
            logger.debug("WalletService.get_or_create_wallet failed: %s — falling back", e)

        Wallet.objects.get_or_create(
            user=instance,
            defaults={'balance': 0}
        )

    except IntegrityError as ie:
        logger.warning("IntegrityError in create_user_wallet signal: %s", ie)
    except Exception as exc:
        logger.exception("Unexpected error in create_user_wallet signal: %s", exc)

