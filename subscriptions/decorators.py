# subscriptions/decorators.py
import logging
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .services import SubscriptionService

logger = logging.getLogger(__name__)


def subscription_required(view_func):
    """
    Decorator to require an active subscription for a view.

    Usage:
        @subscription_required
        def my_view(request): ...
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.info(request, "Please log in to continue.")
            return redirect("users:login")

        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        if not active_subscription:
            messages.warning(request, "You need an active subscription to access this feature.")
            logger.info("User %s attempted to access %s without subscription", request.user.pk, request.path)
            return redirect("subscriptions:plans")

        return view_func(request, *args, **kwargs)

    return _wrapped_view


def plan_required(plan_name):
    """
    Decorator to require a specific subscription plan by name.

    Usage:
        @plan_required("Business Member Plan")
        def my_view(request): ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.info(request, "Please log in to continue.")
                return redirect("users:login")

            active_subscription = SubscriptionService.get_user_active_subscription(request.user)
            if not active_subscription or active_subscription.plan.name != plan_name:
                messages.warning(
                    request,
                    f"You need the {plan_name} plan to access this feature."
                )
                logger.info(
                    "User %s attempted to access %s without required plan %s",
                    request.user.pk, request.path, plan_name
                )
                return redirect("subscriptions:plans")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
