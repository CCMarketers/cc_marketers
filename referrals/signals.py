
import logging
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ReferralCode

logger = logging.getLogger(__name__)
User = get_user_model()


@receiver(post_save, sender=User)
def create_referral_code_for_new_user(sender, instance, created, **kwargs):
    """
    Automatically create a ReferralCode when a new user is created.
    Initial state: can_refer=True, is_active=True
    """
    if created and not hasattr(instance, "referral_code"):
        try:
            ReferralCode.objects.create(
                user=instance,
                is_active=True,
                can_refer=True
            )
            logger.info(f"[SIGNAL] ✅ Referral code auto-created for new user: {instance.username}")
        except Exception as e:
            logger.error(
                f"[SIGNAL] ❌ Failed to create referral code for {instance.username}: {str(e)}",
                exc_info=True
            )

