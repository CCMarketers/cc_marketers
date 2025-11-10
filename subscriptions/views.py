# subscriptions/views.py
# from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
# from django.db.models import Sum
from django.shortcuts import render, redirect
# from django.utils import timezone

from .models import SubscriptionPlan, UserSubscription
from .services import SubscriptionService
from wallets.models import Wallet
# from wallets.services import WalletService
from referrals.services import ReferralEarningService
from tasks.services import TaskWalletService
from referrals.services import ReferralSubscriptionHandler


import logging
logger = logging.getLogger(__name__)

def subscription_plans(request):
    """
    Display available subscription plans + current wallet balance + active sub.
    """
    plans = SubscriptionPlan.objects.filter(is_active=True)
    user_wallet_balance = Decimal("0.00")
    active_subscription = None

    if request.user.is_authenticated:
        wallet = Wallet.objects.filter(user=request.user).first()
        user_wallet_balance = wallet.balance if wallet else Decimal("0.00")
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)

    return render(
        request,
        "subscriptions/plans.html",
        {
            "plans": plans,
            "user_wallet_balance": user_wallet_balance,
            "active_subscription": active_subscription,
        },
    )


@login_required
def subscribe(request, plan_id):
    """
    Subscribe user to a plan (only one active at a time).
    """
    if request.method != "POST":
        return redirect("subscriptions:plans")

    active_subscription = SubscriptionService.get_user_active_subscription(request.user)
    if active_subscription:
        messages.error(
            request,
            f"You already have an active subscription: {active_subscription.plan.name}. "
            "Cancel it before subscribing to a new plan.",
        )
        return redirect("subscriptions:my_subscription")

    result = SubscriptionService.subscribe_user(request.user, plan_id)
    if result.get("success"):
        ReferralEarningService.credit_signup_bonus(request.user)
        messages.success(request, "Successfully subscribed to the plan!")
        return redirect("subscriptions:my_subscription")

    messages.error(request, result.get("error", "Subscription failed."))
    return redirect("subscriptions:plans")


@login_required
def my_subscription(request):
    """
    Display user's current subscription & wallet balance (minus pending withdrawals).
    """
    active_subscription = SubscriptionService.get_user_active_subscription(request.user)
    subscription_history = (
        UserSubscription.objects
        .filter(user=request.user)
        .select_related("plan")              # fetch plan in same query
        .order_by("-start_date")[:20]        # limit to 20 most recent
    )


    wallet = Wallet.objects.filter(user=request.user).first()
    if wallet:
        # pending_withdrawals = WithdrawalRequest.objects.filter(
        #     user=request.user, status="pending"
        # ).aggregate(total=Sum("amount_usd"))["total"] or Decimal("0.00")
        wallet_balance = wallet.get_available_balance
    else:
        wallet_balance = Decimal("0.00")

    return render(
        request,
        "subscriptions/my_subscription.html",
        {
            "active_subscription": active_subscription,
            "subscription_history": subscription_history,
            "wallet_balance": wallet_balance,
        },
    )


@login_required
def toggle_auto_renewal(request):
    """
    Toggle auto-renewal for user's active subscription.
    """
    if request.method == "POST":
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        if not active_subscription:
            messages.error(request, "No active subscription found!")
            return redirect("subscriptions:my_subscription")

        active_subscription.auto_renewal = not active_subscription.auto_renewal
        active_subscription.save(update_fields=["auto_renewal"])

        status = "enabled" if active_subscription.auto_renewal else "disabled"
        messages.success(request, f"Auto-renewal {status} successfully!")

    return redirect("subscriptions:my_subscription")



@login_required
def cancel_subscription(request):
    """
    Cancel user's active subscription.
    ✅ NOW: Only disables referrals, allows reactivation on resubscribe
    """
    if request.method != "POST":
        return redirect("subscriptions:my_subscription")

    active_subscription = SubscriptionService.get_user_active_subscription(request.user)
    if not active_subscription:
        messages.error(request, "No active subscription found!")
        return redirect("subscriptions:my_subscription")
    
    logger.info(
        f"[CANCEL_SUB] User {request.user.username} cancelling "
        f"{active_subscription.plan.name} subscription"
    )

    # Mark subscription as cancelled
    active_subscription.status = "cancelled"
    active_subscription.save(update_fields=["status"])
    
    logger.info(f"[CANCEL_SUB] Subscription cancelled for {request.user.username}")

    # Handle Business Member Account allocation reversal
    if active_subscription.plan.name == "Business Member Account":
        allocation_amount = Decimal("10000.00")
        task_wallet = TaskWalletService.get_or_create_wallet(user=request.user)

        if task_wallet.balance >= allocation_amount:
            # Reverse allocation if unused
            TaskWalletService.debit_wallet(
                user=request.user,
                amount=allocation_amount,
                category="subscription_reversal",
                description=(
                    f"Reversal of monthly allocation from cancelled plan "
                    f"{active_subscription.plan.name}"
                ),
            )
            logger.info(
                f"[CANCEL_SUB] Reversed ₦{allocation_amount} task wallet "
                f"allocation for {request.user.username}"
            )
            messages.info(request, "Business plan allocation reversed successfully.")
        else:
            logger.warning(
                f"[CANCEL_SUB] Cannot reverse allocation for {request.user.username}: "
                f"insufficient balance (₦{task_wallet.balance} < ₦{allocation_amount})"
            )
            messages.warning(
                request,
                "Your subscription was cancelled, but the Task Wallet allocation was already used."
            )
    
    # ✅ FIX: Temporarily disable referrals (can be reactivated on resubscribe)
    logger.info(f"[CANCEL_SUB] Disabling referral privileges for {request.user.username}")
    ReferralSubscriptionHandler.handle_subscription_cancellation(request.user)

    messages.success(
        request, 
        "Subscription cancelled successfully. "
        "You can resubscribe anytime to reactivate your referral code."
    )
    logger.info(f"[CANCEL_SUB] ✅ Cancellation complete for {request.user.username}")
    
    return redirect("subscriptions:my_subscription")