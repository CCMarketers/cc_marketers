# subscriptions/context_processors.py
import logging

from .services import SubscriptionService

logger = logging.getLogger(__name__)


def subscription_context(request):
    """
    Add subscription context to all templates.

    Context:
        user_active_subscription: current active subscription or None
        user_wallet_balance: task wallet balance (Decimal) or 0
    """
    context = {}

    # Only populate for authenticated users
    if not request.user.is_authenticated:
        return context

    # Active subscription (single query)
    active_subscription = SubscriptionService.get_user_active_subscription(request.user)
    context["user_active_subscription"] = active_subscription

    # Wallet balance (try/catch around import and DB)
    balance = 0
    try:
        # Import lazily so tasks app is optional
        from tasks.models import TaskWallet

        wallet = TaskWallet.objects.filter(user=request.user).only("balance").first()
        if wallet:
            balance = wallet.balance
    except ImportError:
        logger.debug("tasks app not installed, skipping TaskWallet lookup")
    except Exception as exc:
        logger.warning("Error fetching TaskWallet for user %s: %s", request.user.pk, exc)

    context["user_wallet_balance"] = balance
    return context
