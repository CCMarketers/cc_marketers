

# subscriptions/views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SubscriptionPlan, UserSubscription
from .services import SubscriptionService
from wallets.models import Wallet 
from django.utils import timezone
from datetime import timedelta
from wallets.services import WalletService  
from referrals.services import credit_signup_bonus_on_subscription
from tasks.services import TaskWalletService
from decimal import Decimal




def subscription_plans(request):
    """Display available subscription plans"""
    plans = SubscriptionPlan.objects.filter(is_active=True)
    user_wallet_balance = 0
    active_subscription = None
    
    if request.user.is_authenticated:
        try:
            wallet = Wallet.objects.get(user=request.user)
            user_wallet_balance = wallet.balance
        except Wallet.DoesNotExist:
            user_wallet_balance = 0
        
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
    
    context = {
        'plans': plans,
        'user_wallet_balance': user_wallet_balance,
        'active_subscription': active_subscription,
    }
    return render(request, 'subscriptions/plans.html', context)

@login_required
def subscribe(request, plan_id):
    """Subscribe user to a plan (only one at a time)"""
    if request.method == 'POST':
        # Check if user already has an active subscription
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        if active_subscription:
            messages.error(
                request,
                f"You already have an active subscription: {active_subscription.plan.name}. "
                "Cancel it before subscribing to a new plan."
            )
            return redirect('subscriptions:my_subscription')

        # Otherwise proceed with subscription
        result = SubscriptionService.subscribe_user(request.user, plan_id)

        if result['success']:
            messages.success(request, 'Successfully subscribed to the plan!')
            credit_signup_bonus_on_subscription(request.user)
            return redirect('subscriptions:my_subscription')
        else:
            messages.error(request, result['error'])
            return redirect('subscriptions:plans')
    
    return redirect('subscriptions:plans')


@login_required
def my_subscription(request):
    """Display user's current subscription"""
    active_subscription = SubscriptionService.get_user_active_subscription(request.user)
    subscription_history = UserSubscription.objects.filter(user=request.user)
    
    try:
        wallet = Wallet.objects.get(user=request.user)
        wallet_balance = wallet.balance
    except Wallet.DoesNotExist:
        wallet_balance = 0
    
    context = {
        'active_subscription': active_subscription,
        'subscription_history': subscription_history,
        'wallet_balance': wallet_balance,
    }
    return render(request, 'subscriptions/my_subscription.html', context)

@login_required
def toggle_auto_renewal(request):
    """Toggle auto-renewal for user's subscription"""
    if request.method == 'POST':
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)
        if active_subscription:
            active_subscription.auto_renewal = not active_subscription.auto_renewal
            active_subscription.save()
            
            status = "enabled" if active_subscription.auto_renewal else "disabled"
            messages.success(request, f'Auto-renewal {status} successfully!')
        else:
            messages.error(request, 'No active subscription found!')
    
    return redirect('subscriptions:my_subscription')

@login_required
def cancel_subscription(request):
    """Cancel user's active subscription (with refund if within 6 hours).
    If Business Plan → ensure $10 Task Wallet allocation is reversed fully.
    """
    if request.method == 'POST':
        active_subscription = SubscriptionService.get_user_active_subscription(request.user)

        if active_subscription:
            now = timezone.now()
            time_diff = now - active_subscription.start_date

            # Cancel subscription
            active_subscription.status = 'cancelled'
            active_subscription.save()

            refund_allowed = True

            # ✅ If Business Member Plan → check Task Wallet balance before refund
            if active_subscription.plan.name == "Business Member Plan":
                task_wallet = TaskWalletService.get_or_create_wallet(user=request.user)
                allocation_amount = Decimal("10.00")

                if task_wallet.balance < allocation_amount:
                    # User already used part/all of the allocation → block refund
                    refund_allowed = False
                    messages.warning(
                        request,
                        "Your subscription was cancelled, but refund is not possible "
                        "because you already spent the Task Wallet allocation."
                    )
                else:
                    # Safe to reverse allocation
                    TaskWalletService.debit_wallet(
                        user=request.user,
                        amount=allocation_amount,
                        category="subscription_allocation_reversal",
                        description=f"Reversal of monthly allocation from cancelled plan {active_subscription.plan.name}"
                    )

            # ✅ Refund only if within 6 hours & allowed
            if refund_allowed and time_diff <= timedelta(hours=6):
                refund_amount = active_subscription.plan.price

                WalletService.credit_wallet(
                    user=request.user,
                    amount=refund_amount,
                    category='subscription_refund',
                    description=f"Refund for {active_subscription.plan.name} (cancelled within 6 hours)",
                    reference=f"REFUND_{request.user.id}_{active_subscription.id}"
                )

                messages.success(
                    request,
                    f'Subscription cancelled. ${refund_amount} refunded to your wallet.'
                )
            elif refund_allowed:
                messages.success(
                    request,
                    'Subscription cancelled successfully (no refund, beyond 6 hours).'
                )

        else:
            messages.error(request, 'No active subscription found!')

    return redirect('subscriptions:my_subscription')
