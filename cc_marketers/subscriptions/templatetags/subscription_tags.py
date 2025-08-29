
# subscriptions/templatetags/subscription_tags.py
from django import template
from subscriptions.services import SubscriptionService

register = template.Library()

@register.simple_tag
def get_user_subscription(user):
    """Get user's active subscription"""
    if user.is_authenticated:
        return SubscriptionService.get_user_active_subscription(user)
    return None

@register.simple_tag
def user_has_subscription(user):
    """Check if user has active subscription"""
    if user.is_authenticated:
        subscription = SubscriptionService.get_user_active_subscription(user)
        return subscription is not None
    return False

@register.simple_tag
def user_has_plan(user, plan_name):
    """Check if user has specific plan"""
    if user.is_authenticated:
        subscription = SubscriptionService.get_user_active_subscription(user)
        return subscription and subscription.plan.name == plan_name
    return False

@register.filter
def can_afford_plan(wallet_balance, plan_price):
    """Check if user can afford a plan"""
    return float(wallet_balance) >= float(plan_price)

