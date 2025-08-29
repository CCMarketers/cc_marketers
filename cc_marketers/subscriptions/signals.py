

# subscriptions/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import UserSubscription

@receiver(post_save, sender=UserSubscription)
def subscription_activated(sender, instance, created, **kwargs):
    """Handle subscription activation"""
    if created and instance.status == 'active':
        # You can add additional logic here when a subscription is activated
        # For example, send welcome email, activate features, etc.
        print(f"New subscription activated for {instance.user.username}: {instance.plan.name}")

