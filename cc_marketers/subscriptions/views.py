# subscriptions/views.py
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import SubscriptionPlan, UserSubscription
from .services import SubscriptionService
from wallets.models import Wallet, WithdrawalRequest
from wallets.services import WalletService
from referrals.services import credit_signup_bonus_on_subscription
from tasks.services import TaskWalletService


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
        credit_signup_bonus_on_subscription(request.user)
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
    subscription_history = UserSubscription.objects.filter(user=request.user)

    wallet = Wallet.objects.filter(user=request.user).first()
    if wallet:
        pending_withdrawals = WithdrawalRequest.objects.filter(
            user=request.user, status="pending"
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        wallet_balance = wallet.balance - pending_withdrawals
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
    Cancel user's active subscription (with refund if within 6 hours).
    If Business Plan → ensure $10 Task Wallet allocation is reversed fully.
    """
    if request.method != "POST":
        return redirect("subscriptions:my_subscription")

    active_subscription = SubscriptionService.get_user_active_subscription(request.user)
    if not active_subscription:
        messages.error(request, "No active subscription found!")
        return redirect("subscriptions:my_subscription")

    now = timezone.now()
    time_diff = now - active_subscription.start_date
    refund_allowed = True

    # Mark subscription as cancelled
    active_subscription.status = "cancelled"
    active_subscription.save(update_fields=["status"])

    # Special handling for Business Member Plan allocation
    if active_subscription.plan.name == "Business Member Plan":
        allocation_amount = Decimal("10.00")
        task_wallet = TaskWalletService.get_or_create_wallet(user=request.user)

        if task_wallet.balance < allocation_amount:
            # User already used allocation → cannot refund
            refund_allowed = False
            messages.warning(
                request,
                "Your subscription was cancelled, but refund is not possible "
                "because you already spent the Task Wallet allocation.",
            )
        else:
            # Reverse allocation
            TaskWalletService.debit_wallet(
                user=request.user,
                amount=allocation_amount,
                category="subscription_allocation_reversal",
                description=(
                    f"Reversal of monthly allocation from cancelled plan "
                    f"{active_subscription.plan.name}"
                ),
            )

    # Refund only if within 6 hours & allowed
    if refund_allowed and time_diff <= timedelta(hours=6):
        refund_amount = active_subscription.plan.price
        WalletService.credit_wallet(
            user=request.user,
            amount=refund_amount,
            category="subscription_refund",
            description=f"Refund for {active_subscription.plan.name} (cancelled within 6 hours)",
            reference=f"REFUND_{request.user.id}_{active_subscription.id}",
        )
        messages.success(
            request, f"Subscription cancelled. ${refund_amount} refunded to your wallet."
        )
    elif refund_allowed:
        messages.success(
            request, "Subscription cancelled successfully (no refund, beyond 6 hours)."
        )

    return redirect("subscriptions:my_subscription")
