# subscriptions/context_processors.py

from .services import SubscriptionService

def subscription_context(request):
    """Add subscription context to all templates"""
    context = {}
    
    if request.user.is_authenticated:
        # This part is fine and makes the first DB query
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        context['user_active_subscription'] = active_subscription

        try:
            from tasks.models import TaskWallet
            try:
                # This makes the second DB query
                wallet = TaskWallet.objects.get(user=request.user)
                context['user_wallet_balance'] = wallet.balance
            except TaskWallet.DoesNotExist:
                context['user_wallet_balance'] = 0
            # Add this general exception handler
            except Exception: 
                # If anything else goes wrong (like a DB connection error),
                # default the balance to 0 instead of crashing.
                context['user_wallet_balance'] = 0
        except ImportError:
            # This handles the case where the tasks app might not be installed
            context['user_wallet_balance'] = 0
    
    return context