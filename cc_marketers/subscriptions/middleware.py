
# subscriptions/middleware.py
from django.shortcuts import redirect
from django.contrib import messages
from .services import SubscriptionService

class SubscriptionMiddleware:
    """Middleware to check subscription status for protected views"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Views that require active subscription
        self.protected_views = [
            # Add your protected view names here
            # 'some_app:protected_view',
        ]

    def __call__(self, request):
        # Check if user needs active subscription for this view
        if (request.user.is_authenticated and 
            request.resolver_match and 
            f"{request.resolver_match.app_name}:{request.resolver_match.url_name}" in self.protected_views):
            
            active_subscription = SubscriptionService.get_user_active_subscription(request.user)
            if not active_subscription:
                messages.warning(request, 'You need an active subscription to access this feature.')
                return redirect('subscriptions:plans')
        
        response = self.get_response(request)
        return response
