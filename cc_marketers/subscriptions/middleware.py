# subscriptions/middleware.py
import logging

from django.shortcuts import redirect
from django.contrib import messages
from django.utils.deprecation import MiddlewareMixin

from .services import SubscriptionService

logger = logging.getLogger(__name__)


class SubscriptionMiddleware(MiddlewareMixin):
    """
    Middleware to check subscription status for protected views.
    Populate `protected_views` with "app_name:url_name" strings for which an active subscription is required.
    """

    def __init__(self, get_response):
        super().__init__(get_response)
        self.protected_views = {
            # e.g. "tasks:create_task",
            # e.g. "jobs:post_job",
        }

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Runs before a view is called. If the user is authenticated and
        the requested view is in `protected_views`, check active subscription.
        """
        if not request.user.is_authenticated:
            return None  # skip unauthenticated users entirely

        resolver = getattr(request, "resolver_match", None)
        if not resolver:
            return None

        view_name = f"{resolver.app_name}:{resolver.url_name}"
        if view_name not in self.protected_views:
            return None

        # Enforce subscription
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        if not active_subscription:
            messages.warning(request, "You need an active subscription to access this feature.")
            logger.info("User %s attempted to access %s without subscription", request.user.pk, view_name)
            return redirect("subscriptions:plans")

        return None  # continue normal processing
