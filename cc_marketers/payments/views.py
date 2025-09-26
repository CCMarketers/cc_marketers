# payments/views.py
import json
import logging
from decimal import Decimal
from typing import Optional

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import PaymentTransaction
from .services import PaystackService, WebhookService, FlutterwaveService
from payments.forms import FundingForm  # existing form
from wallets.models import Wallet, Transaction
from payments.models import PaymentGateway

logger = logging.getLogger(__name__)

# -------------------------
# Local forms (safer parsing)
# -------------------------
class WithdrawalForm(forms.Form):
    amount = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    gateway = forms.CharField(max_length=50, required=True)

    # Optional fields for bank transfer flows (if used)
    bank_code = forms.CharField(max_length=20, required=False)
    account_number = forms.CharField(max_length=20, required=False)


# -------------------------
# Helper utilities
# -------------------------
def _get_active_gateway_by_name(name: str) -> Optional[PaymentGateway]:
    """
    Returns active PaymentGateway instance by case-insensitive name.
    Note: consider adding a DB index on ('name', 'is_active') for performance.
    """
    return PaymentGateway.objects.filter(name__iexact=name, is_active=True).first()


def _cache_bank_list(cache_key: str, fetcher_callable, ttl: int = 300):
    """Generic cache helper for bank lists to reduce API calls."""
    banks = cache.get(cache_key)
    if banks is None:
        try:
            result = fetcher_callable()
            if isinstance(result, dict):
                banks = result.get("data") or result.get("banks") or []
            else:
                banks = result or []
            cache.set(cache_key, banks, ttl)
        except Exception:
            logger.exception("Failed to fetch bank list for %s", cache_key)
            banks = []
    return banks


# -------------------------
# Funding (unified)
# -------------------------
@login_required
def initiate_funding(request):
    """
    Unified funding initiation for Paystack and Flutterwave.
    Shows gateway choice and validates via FundingForm.
    """
    if request.method == "POST":
        form = FundingForm(request.POST)
        if form.is_valid():
            amount: Decimal = form.cleaned_data["amount"]
            gateway_choice: str = form.cleaned_data.get("gateway", "paystack").lower()

            callback_url = None
            service = None
            try:
                if gateway_choice == "flutterwave":
                    service = FlutterwaveService()
                    callback_url = request.build_absolute_uri(reverse("payments:flutterwave_callback"))
                else:  # default to paystack
                    service = PaystackService()
                    callback_url = request.build_absolute_uri(reverse("payments:payment_callback"))

                result = service.initialize_payment(user=request.user, amount=amount, callback_url=callback_url)
            except Exception as exc:
                logger.exception("Error initializing payment for user %s via %s: %s", request.user.id, gateway_choice, exc)
                messages.error(request, "Unable to initialize payment. Please try again later.")
                return render(request, "wallets/fund_wallet.html", {"form": form, "show_gateway_choice": True})

            if not result.get("success"):
                messages.error(request, f"Payment initialization failed: {result.get('error', 'Unknown error')}")
                return render(request, "wallets/fund_wallet.html", {"form": form, "show_gateway_choice": True})

            # Gateway-specific redirect URL keys
            redirect_url = (
                result.get("data", {}).get("payment_link")
                or result.get("data", {}).get("authorization_url")
                or result.get("data", {}).get("auth_url")
            )

            if redirect_url:
                return redirect(redirect_url)

            logger.warning("Payment initialized but no redirect URL: result=%s user=%s gateway=%s", result, request.user.id, gateway_choice)
            messages.error(request, "Payment initialized but no payment link was returned. Please try again.")
        # form invalid -> fall through and re-render
        return render(request, "wallets/fund_wallet.html", {"form": form, "show_gateway_choice": True})

    # GET
    return render(request, "wallets/fund_wallet.html", {"form": FundingForm(), "show_gateway_choice": True})


# -------------------------
# Callbacks
# -------------------------
@login_required
def payment_callback(request):
    """
    Paystack callback after authorization.
    Only verifies reference and lets webhook complete wallet crediting.
    """
    reference = request.GET.get("reference")
    if not reference:
        messages.error(request, "Invalid payment reference.")
        return redirect("wallets:dashboard")

    try:
        PaymentTransaction.objects.get(gateway_reference=reference, user=request.user)
    except PaymentTransaction.DoesNotExist:
        messages.error(request, "Transaction not found.")
        return redirect("wallets:dashboard")
    except Exception as exc:
        logger.exception("Error fetching transaction for reference %s: %s", reference, exc)
        messages.error(request, "An internal error occurred.")
        return redirect("wallets:dashboard")

    try:
        paystack_service = PaystackService()
        verification = paystack_service.verify_payment(reference)
        status = (verification.get("success") and verification.get("data", {}).get("data", {}).get("status"))
        if status == "success":
            messages.success(request, "Payment successful! Wallet will be credited shortly.")
        else:
            logger.info("Paystack verification returned non-success for ref=%s: %s", reference, verification)
            messages.error(request, "Payment verification failed.")
    except Exception as exc:
        logger.exception("Error verifying paystack payment for ref %s: %s", reference, exc)
        messages.error(request, "An error occurred during payment verification.")

    return redirect("wallets:dashboard")

@login_required
def flutterwave_callback(request):
    """
    Handle Flutterwave callback after payment.
    Use webhook as source of truth, but verify here for user feedback.
    """
    tx_ref = request.GET.get("tx_ref")
    transaction_id = request.GET.get("transaction_id")
    request.GET.get("status")

    if not tx_ref:
        messages.error(request, "Invalid payment reference")
        return redirect("wallets:dashboard")

    try:
        txn = PaymentTransaction.objects.get(
            gateway_reference=tx_ref,
            user=request.user
        )
    except PaymentTransaction.DoesNotExist:
        messages.error(request, "Transaction not found")
        return redirect("wallets:dashboard")
    except Exception as exc:
        logger.exception("Error fetching transaction for tx_ref %s: %s", tx_ref, exc)
        messages.error(request, "An internal error occurred.")
        return redirect("wallets:dashboard")

    # ✅ First check DB (webhook may have updated it already)
    if txn.status == PaymentTransaction.Status.SUCCESS:
        messages.success(request, "Payment completed successfully! Your wallet has been credited.")
        return redirect("wallets:dashboard")

    # ✅ If no transaction_id, just inform the user
    if not transaction_id:
        messages.warning(request, "Payment is still being verified. Please refresh shortly.")
        return redirect("wallets:dashboard")

    try:
        flutterwave_service = FlutterwaveService()
        verification = flutterwave_service.verify_payment(transaction_id)

        if (
            verification.get("status") == "success"
            and verification.get("data", {}).get("status") == "successful"
        ):
            messages.success(request, "Payment successful! Wallet will be credited shortly.")
        else:
            messages.warning(request, "Payment is being verified. Please check again in a moment.")
    except Exception as exc:
        logger.exception("Error in Flutterwave callback: %s", exc)
        messages.error(request, "An error occurred during payment verification")

    return redirect("wallets:dashboard")

# -------------------------
# Withdrawals
# -------------------------
@login_required
@transaction.atomic
def withdraw_funds(request):
    """
    Handles wallet withdrawal requests.
    Uses a form for input validation and database row locking for correctness.
    """
    if request.method != "POST":
        return redirect("wallets:dashboard")

    form = WithdrawalForm(request.POST)
    if not form.is_valid():
        for field, errs in form.errors.items():
            messages.error(request, f"{field}: {', '.join(errs)}")
        return redirect("wallets:dashboard")

    amount: Decimal = form.cleaned_data["amount"]
    gateway_name: str = form.cleaned_data["gateway"]

    try:
        # Lock wallet row to prevent race conditions; ensure Wallet has an index on user
        wallet = Wallet.objects.select_for_update().get(user=request.user)
    except Wallet.DoesNotExist:
        messages.error(request, "Wallet not found.")
        return redirect("wallets:dashboard")
    except Exception as exc:
        logger.exception("Error obtaining wallet for user %s: %s", request.user.id, exc)
        messages.error(request, "An internal error occurred.")
        return redirect("wallets:dashboard")

    if amount <= 0:
        messages.error(request, "Invalid withdrawal amount.")
        return redirect("wallets:dashboard")

    if wallet.balance < amount:
        messages.error(request, "Insufficient balance.")
        return redirect("wallets:dashboard")

    # Create pending transaction and debit wallet within the atomic context
    try:
        wallet.balance -= amount
        wallet.save(update_fields=["balance"])

        txn = Transaction.objects.create(
            wallet=wallet,
            amount=amount,
            txn_type="withdrawal",
            status="pending",
            gateway=gateway_name,
        )

        gateway = _get_active_gateway_by_name(gateway_name)
        if not gateway:
            logger.warning("Gateway not found or inactive: %s", gateway_name)
            # refund balance
            wallet.balance += amount
            wallet.save(update_fields=["balance"])
            txn.status = "failed"
            txn.response = "Gateway not available"
            txn.save(update_fields=["status", "response"])
            messages.error(request, "Payment gateway not available.")
            return redirect("wallets:dashboard")

        # Call the appropriate service; services should return (success: bool, response: dict/str)
        if gateway.name.lower() == "flutterwave":
            success, response = FlutterwaveService.initiate_transfer(request.user, amount, txn.id, gateway.config)
        elif gateway.name.lower() == "paystack":
            success, response = PaystackService.initiate_transfer(request.user, amount, txn.id, gateway.config)
        else:
            success, response = False, "Unsupported gateway."

        if success:
            txn.status = "success"
            messages.success(request, f"Withdrawal of {amount} successful via {gateway.name}.")
        else:
            # refund
            wallet.balance += amount
            wallet.save(update_fields=["balance"])
            txn.status = "failed"
            messages.error(request, f"Withdrawal failed: {response}")

        txn.response = json.dumps(response) if not isinstance(response, str) else str(response)
        txn.save(update_fields=["status", "response"])

    except Exception as exc:
        logger.exception("Error processing withdrawal for user %s: %s", request.user.id, exc)
        # On unexpected exception, attempt to refund if wallet exists and transaction created
        try:
            if wallet:
                wallet.refresh_from_db()
        except Exception:
            logger.exception("Error refreshing wallet after exception for user %s", request.user.id)
        messages.error(request, "An unexpected error occurred while processing your withdrawal.")

    return redirect("wallets:dashboard")


# -------------------------
# Bank endpoints & verification (cached)
# -------------------------
@login_required
def get_banks(request):
    """
    Get bank list (Paystack). Cached to reduce API calls.
    """
    banks = _cache_bank_list("paystack_banks", lambda: PaystackService().get_banks())
    return JsonResponse({"banks": banks})


@login_required
def get_flutterwave_banks(request):
    """
    Get bank list (Flutterwave). Cached similarly.
    """
    banks = _cache_bank_list("flutterwave_banks", lambda: FlutterwaveService().get_banks())
    return JsonResponse({"success": bool(banks), "banks": banks})


@login_required
@require_http_methods(["POST"])
def verify_account(request):
    """
    Verify account via Paystack (expects JSON body). Protected and validated.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    account_number = data.get("account_number")
    bank_code = data.get("bank_code")
    if not account_number or not bank_code:
        return JsonResponse({"success": False, "error": "Missing parameters"}, status=400)

    try:
        result = PaystackService().resolve_account_number(account_number, bank_code)
        if result and result.get("status"):
            return JsonResponse({"success": True, "account_name": result["data"]["account_name"]})
    except Exception as exc:
        logger.exception("Error resolving account via Paystack: %s", exc)
        return JsonResponse({"success": False, "error": "Internal error"}, status=500)

    return JsonResponse({"success": False, "error": "Invalid account details"}, status=400)


@login_required
@require_http_methods(["POST"])
def verify_flutterwave_account(request):
    """
    Verify account via Flutterwave (expects JSON body).
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    account_number = data.get("account_number")
    bank_code = data.get("bank_code")
    if not account_number or not bank_code:
        return JsonResponse({"success": False, "error": "Missing parameters"}, status=400)

    try:
        result = FlutterwaveService().resolve_account_number(account_number, bank_code)
        if result and result.get("success"):
            return JsonResponse({"success": True, "account_name": result["data"]["account_name"]})
    except Exception as exc:
        logger.exception("Error resolving account via Flutterwave: %s", exc)
        return JsonResponse({"success": False, "error": "Internal error"}, status=500)

    return JsonResponse({"success": False, "error": result.get("error", "Invalid account details")}, status=400)


# -------------------------
# Webhooks (signature-verified, CSRF exempt)
# -------------------------
@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook(request):
    signature = request.META.get("HTTP_X_PAYSTACK_SIGNATURE")
    if not signature:
        logger.warning("Missing Paystack signature header")
        return HttpResponse("No signature", status=400)

    try:
        if not WebhookService.verify_paystack_signature(request.body, signature):
            logger.warning("Invalid Paystack signature")
            return HttpResponse("Invalid signature", status=400)

        event_data = json.loads(request.body)
        result = WebhookService.process_paystack_webhook(event_data)
        if result.get("success"):
            return HttpResponse("OK", status=200)
        logger.warning("Paystack webhook processing returned error: %s", result)
        return HttpResponse(result.get("error", "Error"), status=400)
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in Paystack webhook")
        return HttpResponse("Invalid JSON", status=400)
    except Exception as exc:
        logger.exception("Internal error in Paystack webhook: %s", exc)
        return HttpResponse("Internal error", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def flutterwave_webhook(request):
    signature = request.META.get("HTTP_VERIF_HASH")
    if not signature:
        logger.warning("Missing Flutterwave signature header")
        return HttpResponse("No signature", status=400)

    try:
        if not WebhookService.verify_flutterwave_signature(request.body, signature):
            logger.warning("Invalid Flutterwave signature")
            return HttpResponse("Invalid signature", status=400)

        event_data = json.loads(request.body)
        result = WebhookService.process_flutterwave_webhook(event_data)
        if result.get("success"):
            return HttpResponse("OK", status=200)
        logger.warning("Flutterwave webhook processing returned error: %s", result)
        return HttpResponse(result.get("error", "Error"), status=400)
    except json.JSONDecodeError:
        logger.exception("Invalid JSON in Flutterwave webhook")
        return HttpResponse("Invalid JSON", status=400)
    except Exception as exc:
        logger.exception("Internal error in Flutterwave webhook: %s", exc)
        return HttpResponse("Internal error", status=500)


# -------------------------
# Transaction views (optimized)
# -------------------------
@login_required
def transaction_history(request):
    """
    List user's transactions. select_related used to avoid N+1 on gateway relationship.
    """
    transactions = (
        PaymentTransaction.objects.filter(user=request.user)
        .select_related("gateway")
        .order_by("-created_at")
    )
    return render(request, "payments/transaction_history.html", {"transactions": transactions})


@login_required
def transaction_detail(request, transaction_id):
    transaction = get_object_or_404(PaymentTransaction, id=transaction_id, user=request.user)
    return render(request, "payments/transaction_detail.html", {"transaction": transaction})
