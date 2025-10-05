# subscriptions/signals.py
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserSubscription

logger = logging.getLogger(__name__)

@receiver(post_save, sender=UserSubscription, dispatch_uid="subscription_activated_signal")
def subscription_activated(sender, instance, created, **kwargs):
    """
    Handle subscription activation (fires only on creation).
    Add any onboarding logic here: send email, allocate benefits, etc.
    """
    if created and instance.status == 'active':
        try:
            logger.info(
                f"New subscription activated for {instance.user.username}: {instance.plan.name}"
            )
            # TODO: send welcome email, allocate benefits, etc.
        except Exception as e:
            # Never let signal exceptions break model save
            logger.error(f"Subscription activation signal failed: {e}")
