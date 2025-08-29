
# subscriptions/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .services import SubscriptionService

def subscription_required(view_func):
    """Decorator to require active subscription for a view"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        if not active_subscription:
            messages.warning(request, 'You need an active subscription to access this feature.')
            return redirect('subscriptions:plans')
        
        return view_func(request, *args, **kwargs)
    
    return _wrapped_view


def plan_required(plan_name):
    """Decorator to require specific subscription plan"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            active_subscription = SubscriptionService.get_user_active_subscription(request.user)
            if not active_subscription or active_subscription.plan.name != plan_name:
                messages.warning(request, f'You need the {plan_name} to access this feature.')
                return redirect('subscriptions:plans')
            
            return view_func(request, *args, **kwargs)
        
        return _wrapped_view
    return decorator

