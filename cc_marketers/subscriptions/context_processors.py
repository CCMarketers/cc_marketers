

# subscriptions/context_processors.py
from .services import SubscriptionService

def subscription_context(request):
    """Add subscription context to all templates"""
    context = {}
    
    if request.user.is_authenticated:
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        context['user_active_subscription'] = active_subscription
        
        # Add wallet balance if wallet app exists
        try:
            from wallets.models import TaskWallet
            wallet = TaskWallet.objects.get(user=request.user)
            context['user_wallet_balance'] = wallet.balance
        except:  # noqa: E722
            context['user_wallet_balance'] = 0
    
    return context

