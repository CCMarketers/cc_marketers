# payments/services.py
import logging
import hmac
import hashlib
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    PaymentTransaction,
    PaystackTransaction,
    PaymentGateway,
    WebhookEvent,
    FlutterwaveTransaction,    
)
logger = logging.getLogger(__name__)

# Default HTTP timeout (seconds) for requests to external services
HTTP_TIMEOUT = getattr(settings, "PAYMENT_HTTP_TIMEOUT", 15)


def _safe_json(response: requests.Response) -> Dict[str, Any]:
    """Safely parse JSON response; return empty dict on failure."""
    try:
        return response.json() if response.content else {}
    except ValueError:
        logger.warning("Non-JSON response from %s (status=%s)", response.url, response.status_code)
        return {}


def _ok_resp(response: requests.Response) -> bool:
    """Simple helper: treat 200-299 as OK for many Paystack endpoints (we still check payload status where needed)."""
    return 200 <= response.status_code < 300


class PaystackService:
    """Service class for Paystack API integration.

    Methods return a consistent structure:
        {"success": bool, "data": {...}, "error": "message"}
    """

    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = getattr(settings, "PAYSTACK_PUBLIC_KEY", None)
        self.base_url = "https://api.paystack.co"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        })

    # ------------------------
    # Helpers
    # ------------------------
    def _get_gateway(self):
        try:
            return PaymentGateway.objects.get(name__iexact="paystack")
        except PaymentGateway.DoesNotExist:
            logger.error("Paystack PaymentGateway not configured in DB")
            return None

    # ------------------------
    # Initialize funding (checkout)
    # ------------------------
    def initialize_payment(self, user, amount, currency="NGN", callback_url=None):
        """
        Initialize a payment transaction with Paystack.

        Returns:
            {"success": bool, "data": {...}, "error": str}
        """
        try:
            gateway = self._get_gateway()
            if not gateway:
                return {"success": False, "data": {}, "error": "Payment gateway not configured"}

            # Normalise amount to Decimal
            try:
                amount_dec = Decimal(amount)
            except (InvalidOperation, TypeError):
                return {"success": False, "data": {}, "error": "Invalid amount"}

            with transaction.atomic():
                # Create local pending PaymentTransaction
                payment_transaction = PaymentTransaction.objects.create(
                    user=user,
                    gateway=gateway,
                    transaction_type=PaymentTransaction.TransactionType.FUNDING,
                    amount=amount_dec,
                    currency=currency,
                    gateway_reference=f"PS_{timezone.now().strftime('%Y%m%d%H%M%S')}_{str(user.id)[:8]}",
                    status=PaymentTransaction.Status.PENDING,
                )

                url = f"{self.base_url}/transaction/initialize"
                payload = {
                    "email": user.email,
                    "amount": int(amount_dec * Decimal("100")),  # convert to kobo
                    "currency": currency,
                    "reference": payment_transaction.gateway_reference,
                    "callback_url": callback_url,
                    "metadata": {
                        "user_id": str(user.id),
                        "transaction_id": str(payment_transaction.id),
                        "purpose": "wallet_funding",
                        "internal_reference": payment_transaction.internal_reference,
                    },
                }

                resp = self.session.post(url, json=payload, timeout=HTTP_TIMEOUT)
                resp_data = _safe_json(resp)

                if _ok_resp(resp) and resp_data.get("status") is True:
                    pay_data = resp_data.get("data", {})
                    # Defensive check for authorization_url
                    if "authorization_url" not in pay_data:
                        # mark txn failed and return
                        payment_transaction.status = PaymentTransaction.Status.FAILED
                        payment_transaction.gateway_response = resp_data
                        payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])
                        err = "Missing authorization URL from gateway"
                        logger.error(err + " - resp: %s", resp_data)
                        return {"success": False, "data": resp_data, "error": err}

                    # Persist PaystackTransaction
                    PaystackTransaction.objects.create(
                        transaction=payment_transaction,
                        authorization_url=pay_data.get("authorization_url"),
                        access_code=pay_data.get("access_code"),
                        paystack_reference=pay_data.get("reference") or "",
                    )

                    payment_transaction.gateway_response = resp_data
                    payment_transaction.save(update_fields=["gateway_response", "updated_at"])

                    return {
                        "success": True,
                        "data": {
                            "transaction_id": str(payment_transaction.id),
                            "internal_reference": payment_transaction.internal_reference,
                            "gateway_reference": payment_transaction.gateway_reference,
                            "authorization_url": pay_data.get("authorization_url"),
                            "access_code": pay_data.get("access_code"),
                            "reference": pay_data.get("reference"),
                            "raw": resp_data,
                        },
                        "error": None,
                    }

                # Failure path: mark txn failed
                payment_transaction.status = PaymentTransaction.Status.FAILED
                payment_transaction.gateway_response = resp_data
                payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])

                err_msg = resp_data.get("message") or resp_data.get("error") or "Payment initialization failed"
                logger.info("Paystack init failed: %s", err_msg)
                return {"success": False, "data": resp_data, "error": err_msg}

        except requests.RequestException as exc:
            logger.exception("HTTP error during payment initialization: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error in initialize_payment: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Verify payment status
    # ------------------------
    def verify_payment(self, reference: str) -> Dict[str, Any]:
        """
        Verify a payment with Paystack.
        Returns {"success": bool, "data": {...}, "error": str}
        """
        try:
            url = f"{self.base_url}/transaction/verify/{reference}"
            resp = self.session.get(url, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)

            ok = _ok_resp(resp) and resp_data.get("status", False)
            return {"success": ok, "data": resp_data, "error": None if ok else resp_data.get("message", "Verification failed")}
        except requests.RequestException as exc:
            logger.exception("HTTP error during payment verification: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error during payment verification: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Create transfer recipient
    # ------------------------
    def create_transfer_recipient(self, user, bank_code: str, account_number: str) -> Dict[str, Any]:
        """Create a transfer recipient (nuban) for withdrawals."""
        try:
            url = f"{self.base_url}/transferrecipient"
            payload = {
                "type": "nuban",
                "name": f"{user.first_name} {user.last_name}".strip() or getattr(user, "username", str(user.id)),
                "account_number": account_number,
                "bank_code": bank_code,
                "currency": "NGN",
                "metadata": {"user_id": str(user.id)},
            }
            resp = self.session.post(url, json=payload, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)
            ok = _ok_resp(resp) and resp_data.get("status", False)

            if ok:
                return {"success": True, "data": resp_data.get("data", {}), "error": None}
            return {"success": False, "data": resp_data, "error": resp_data.get("message", "Failed to create recipient")}
        except requests.RequestException as exc:
            logger.exception("HTTP error creating transfer recipient: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error creating transfer recipient: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Initiate transfer (withdrawal)
    # ------------------------
    def initiate_transfer(self, user, amount, recipient_code: str, reason: str = "Wallet withdrawal") -> Dict[str, Any]:
        """
        Initiate a transfer to a recipient (withdrawal).
        Creates a PENDING PaymentTransaction and PaystackTransaction on acknowledgement.
        """
        try:
            gateway = self._get_gateway()
            if not gateway:
                return {"success": False, "data": {}, "error": "Payment gateway not configured"}

            try:
                amount_dec = Decimal(amount)
            except (InvalidOperation, TypeError):
                return {"success": False, "data": {}, "error": "Invalid amount"}

            with transaction.atomic():
                payment_transaction = PaymentTransaction.objects.create(
                    user=user,
                    gateway=gateway,
                    transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
                    amount=amount_dec,
                    currency="NGN",
                    gateway_reference=f"WD_{timezone.now().strftime('%Y%m%d%H%M%S')}_{str(user.id)[:8]}",
                    status=PaymentTransaction.Status.PENDING,
                )

                url = f"{self.base_url}/transfer"
                payload = {
                    "source": "balance",
                    "amount": int(amount_dec * Decimal("100")),  # kobo
                    "recipient": recipient_code,
                    "reason": reason,
                    "reference": payment_transaction.gateway_reference,
                }

                resp = self.session.post(url, json=payload, timeout=HTTP_TIMEOUT)
                resp_data = _safe_json(resp)

                if _ok_resp(resp) and resp_data.get("status", False):
                    pay_data = resp_data.get("data", {})
                    PaystackTransaction.objects.create(
                        transaction=payment_transaction,
                        paystack_reference=pay_data.get("reference") or "",
                        transfer_code=pay_data.get("transfer_code") or "",
                    )

                    payment_transaction.gateway_response = resp_data
                    payment_transaction.save(update_fields=["gateway_response", "updated_at"])
                    return {
                        "success": True,
                        "data": {
                            "transaction_id": str(payment_transaction.id),
                            "internal_reference": payment_transaction.internal_reference,
                            "gateway_reference": payment_transaction.gateway_reference,
                            "paystack_reference": pay_data.get("reference"),
                            "transfer_code": pay_data.get("transfer_code"),
                            "status": pay_data.get("status"),
                            "raw": resp_data,
                        },
                        "error": None,
                    }

                # Mark as failed and persist response
                payment_transaction.status = PaymentTransaction.Status.FAILED
                payment_transaction.gateway_response = resp_data
                payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])

                err = resp_data.get("message") or "Transfer initiation failed"
                logger.info("Paystack transfer failed: %s", err)
                return {"success": False, "data": resp_data, "error": err}

        except requests.RequestException as exc:
            logger.exception("HTTP error initiating transfer: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error initiating transfer: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Get banks
    # ------------------------
    def get_banks(self) -> Dict[str, Any]:
        """Return list of banks from Paystack (data list)"""
        try:
            url = f"{self.base_url}/bank"
            resp = self.session.get(url, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)
            ok = _ok_resp(resp)

            if ok and isinstance(resp_data.get("data", None), list):
                return {"success": True, "data": resp_data.get("data", []), "error": None}
            return {"success": False, "data": [], "error": resp_data.get("message", "Failed to fetch banks")}
        except requests.RequestException as exc:
            logger.exception("HTTP error fetching banks: %s", exc)
            return {"success": False, "data": [], "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error fetching banks: %s", exc)
            return {"success": False, "data": [], "error": str(exc)}

    # ------------------------
    # Resolve account number
    # ------------------------
    def resolve_account_number(self, account_number: str, bank_code: str) -> Dict[str, Any]:
        """Resolve an account number to an account name."""
        try:
            url = f"{self.base_url}/bank/resolve"
            params = {"account_number": account_number, "bank_code": bank_code}
            resp = self.session.get(url, params=params, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)
            ok = _ok_resp(resp) and resp_data.get("status", False)

            if ok:
                # Paystack returns { "status": True, "message": "...", "data": { "account_name": "...", ... } }
                return {"success": True, "data": resp_data.get("data", {}), "error": None}
            return {"success": False, "data": {}, "error": resp_data.get("message", "Resolve failed")}
        except requests.RequestException as exc:
            logger.exception("HTTP error resolving account: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error resolving account: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}




class WebhookService:
    """Service for handling payment webhooks (Paystack & Flutterwave)."""

    @staticmethod
    def verify_paystack_signature(payload: bytes, signature: str) -> bool:
        """Verify Paystack webhook signature using HMAC-SHA512."""
        secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "")
        if not secret_key:
            logger.error("PAYSTACK_SECRET_KEY not set in settings")
            return False

        computed_signature = hmac.new(
            secret_key.encode("utf-8"),
            payload,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(computed_signature, signature)

    @staticmethod
    def process_paystack_webhook(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming Paystack webhook JSON and handle idempotency."""
        event_type = event_data.get("event")
        data = event_data.get("data", {}) or {}
        reference = data.get("reference")
        if not reference:
            logger.warning("Webhook missing reference: %s", event_data)
            return {"success": False, "error": "No reference found", "data": {}}

        gateway = PaymentGateway.objects.filter(name__iexact="paystack").first()
        if not gateway:
            logger.error("Webhook received but PaymentGateway 'paystack' not configured")
            return {"success": False, "error": "Gateway not configured", "data": {}}

        webhook_event, created = WebhookEvent.objects.get_or_create(
            gateway=gateway,
            reference=reference,
            defaults={"event_type": event_type, "payload": event_data},
        )

        if webhook_event.processed:
            # Already handled; idempotent behavior
            logger.info("Duplicate webhook ignored for reference %s", reference)
            return {"success": True, "message": "Duplicate event ignored", "data": {}}

        try:
            if event_type == "charge.success":
                result = WebhookService._handle_successful_charge(data, webhook_event)
            elif event_type == "transfer.success":
                result = WebhookService._handle_successful_transfer(data, webhook_event)
            elif event_type in ("transfer.failed", "transfer.reversed"):
                result = WebhookService._handle_failed_transfer(data, webhook_event)
            else:
                # Unhandled event recorded for audit
                webhook_event.event_type = WebhookEvent.EventType.OTHER
                webhook_event.payload = event_data
                webhook_event.save(update_fields=["event_type", "payload"])
                result = {"success": True, "message": "Unhandled event recorded", "data": {}}

            return result
        except Exception as exc:
            logger.exception("Error processing webhook for reference %s: %s", reference, exc)
            return {"success": False, "error": str(exc), "data": {}}

    # -----------------
    # Paystack event handlers
    # -----------------
    @staticmethod
    @transaction.atomic
    def _handle_successful_charge(data: Dict[str, Any], webhook_event: WebhookEvent) -> Dict[str, Any]:
        reference = data.get("reference")
        # Paystack sends amount in kobo; convert to naira
        amount = Decimal(str(data.get("amount", 0))) / Decimal("100")

        try:
            payment_txn = PaymentTransaction.objects.select_for_update().get(
                gateway_reference=reference,
                transaction_type=PaymentTransaction.TransactionType.FUNDING,
            )
        except PaymentTransaction.DoesNotExist:
            logger.warning("PaymentTransaction not found for reference %s", reference)
            return {"success": False, "error": "PaymentTransaction not found", "data": {}}

        if payment_txn.status == PaymentTransaction.Status.SUCCESS:
            webhook_event.processed = True
            webhook_event.save(update_fields=["processed"])
            return {"success": True, "message": "Already processed", "data": {}}

        # Mark success on payment transaction
        payment_txn.status = PaymentTransaction.Status.SUCCESS
        payment_txn.completed_at = timezone.now()
        payment_txn.gateway_response = data
        payment_txn.save(update_fields=["status", "completed_at", "gateway_response"])

        # Credit wallet
        from wallets.services import WalletService

        WalletService.credit_wallet(
            user=payment_txn.user,
            amount=amount,
            category="funding",
            description=f"Wallet funding via {PaymentGateway.name} (Ref: {reference})",
            reference=payment_txn.internal_reference,
            payment_transaction=payment_txn,
        )

        # Mark webhook processed
        webhook_event.processed = True
        webhook_event.processed_at = timezone.now()
        webhook_event.payload = data
        webhook_event.save(update_fields=["processed", "processed_at", "payload"])

        return {"success": True, "message": "Wallet funded successfully", "data": {"reference": reference}}

    @staticmethod
    def _handle_successful_transfer(data: Dict[str, Any], webhook_event: WebhookEvent) -> Dict[str, Any]:
        """Handle successful Paystack withdrawal transfer webhook."""
        reference = data.get("reference")
        try:
            with transaction.atomic():
                payment_txn = (
                    PaymentTransaction.objects.select_for_update()
                    .get(gateway_reference=reference, transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL)
                )

                if payment_txn.status == PaymentTransaction.Status.PENDING:
                    payment_txn.status = PaymentTransaction.Status.SUCCESS
                    payment_txn.completed_at = timezone.now()
                    payment_txn.gateway_response = data
                    payment_txn.save(update_fields=["status", "completed_at", "gateway_response"])

                    # Mark any matching WithdrawalRequest as approved (if present)
                    from wallets.models import WithdrawalRequest

                    withdrawal = WithdrawalRequest.objects.filter(gateway_reference=reference).first()
                    if withdrawal:
                        withdrawal.status = "approved"
                        withdrawal.processed_at = withdrawal.processed_at or timezone.now()
                        withdrawal.gateway_response = data
                        withdrawal.save(update_fields=["status", "processed_at", "gateway_response"])

                    webhook_event.processed = True
                    webhook_event.processed_at = timezone.now()
                    webhook_event.payload = data
                    webhook_event.save(update_fields=["processed", "processed_at", "payload"])
                    return {"success": True, "message": "Transfer processed successfully", "data": {}}

                return {"success": True, "message": "Transfer already processed", "data": {}}
        except PaymentTransaction.DoesNotExist:
            logger.warning("Withdrawal transaction not found for reference %s", reference)
            return {"success": False, "error": "Withdrawal transaction not found", "data": {}}

    @staticmethod
    def _handle_failed_transfer(data: Dict[str, Any], webhook_event: WebhookEvent) -> Dict[str, Any]:
        """Handle failed or reversed Paystack withdrawal webhook; refund user."""
        reference = data.get("reference")
        from wallets.services import WalletService
        from wallets.models import WithdrawalRequest

        try:
            with transaction.atomic():
                payment_txn = (
                    PaymentTransaction.objects.select_for_update()
                    .get(gateway_reference=reference, transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL)
                )

                if payment_txn.status == PaymentTransaction.Status.PENDING:
                    payment_txn.status = PaymentTransaction.Status.FAILED
                    payment_txn.gateway_response = data
                    payment_txn.save(update_fields=["status", "gateway_response"])

                    # Refund the user's wallet
                    WalletService.credit_wallet(
                        user=payment_txn.user,
                        amount=payment_txn.amount,
                        category="withdrawal_refund",
                        description=f"Refund for failed withdrawal (Ref: {reference})",
                        reference=payment_txn.internal_reference,
                        payment_transaction=payment_txn,
                    )

                    withdrawal = WithdrawalRequest.objects.filter(gateway_reference=reference).first()
                    if withdrawal:
                        withdrawal.status = "rejected"
                        withdrawal.processed_at = timezone.now()
                        withdrawal.gateway_response = data
                        withdrawal.save(update_fields=["status", "processed_at", "gateway_response"])

                    webhook_event.processed = True
                    webhook_event.processed_at = timezone.now()
                    webhook_event.payload = data
                    webhook_event.save(update_fields=["processed", "processed_at", "payload"])
                    return {"success": True, "message": "Failed transfer processed (refund issued)", "data": {}}

                return {"success": True, "message": "Failed transfer already processed", "data": {}}
        except PaymentTransaction.DoesNotExist:
            logger.warning("Withdrawal transaction not found for failed transfer reference %s", reference)
            return {"success": False, "error": "Withdrawal transaction not found", "data": {}}

    # -----------------
    # Flutterwave signature & processing
    # -----------------

    @staticmethod
    def verify_flutterwave_signature(payload: bytes, signature: str) -> bool:
        """Verify Flutterwave webhook signature (simple header match)."""
        secret_hash = getattr(settings, "FLUTTERWAVE_SECRET_HASH", "")
        if not secret_hash:
            logger.error("FLUTTERWAVE_SECRET_HASH not set in settings")
            return False

        return hmac.compare_digest(signature, secret_hash)

    @staticmethod
    def process_flutterwave_webhook(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming Flutterwave webhook JSON and handle idempotency."""
        # Flutterwave sometimes sends 'event' or 'event.type'
        event_type = (
            event_data.get("event")
            or event_data.get("event.type")
            or "unknown"
        )

        # Some webhooks wrap data inside "data", others send fields at the root
        data = event_data.get("data") or event_data

        # Normalize tx_ref lookup
        tx_ref = (
            data.get("tx_ref")
            or data.get("txRef")
            or data.get("flw_ref")
            or data.get("flwRef")
            or data.get("reference")
            or data.get("orderRef")
        )


        if not tx_ref:
            logger.warning("Flutterwave webhook missing tx_ref: %s", event_data)
            return {"success": False, "error": "No tx_ref found", "data": {}}

        gateway = PaymentGateway.objects.filter(name__iexact="flutterwave").first()
        if not gateway:
            logger.error("Webhook received but PaymentGateway 'flutterwave' not configured")
            return {"success": False, "error": "Gateway not configured", "data": {}}

        webhook_event, created = WebhookEvent.objects.get_or_create(
            gateway=gateway,
            reference=tx_ref,
            defaults={"event_type": event_type, "payload": event_data},
        )

        if webhook_event.processed:
            logger.info("Duplicate Flutterwave webhook ignored for reference %s", tx_ref)
            return {"success": True, "message": "Duplicate event ignored", "data": {}}

        try:
            status = data.get("status", "").lower()

            # Card/charge payment
            if event_type == "charge.completed" and status == "successful":
                result = WebhookService._handle_successful_flutterwave_charge(data, webhook_event)

            # Bank transfer webhook (your current payload)
            elif event_type == "BANK_TRANSFER_TRANSACTION" and status == "successful":
                result = WebhookService._handle_successful_flutterwave_charge(data, webhook_event)

            # Transfers
            elif event_type == "transfer.completed":
                if status == "successful":
                    result = WebhookService._handle_successful_flutterwave_transfer(data, webhook_event)
                elif status in ["failed", "cancelled"]:
                    result = WebhookService._handle_failed_flutterwave_transfer(data, webhook_event)
                else:
                    result = {"success": True, "message": "Unhandled transfer status", "data": data}
            else:
                webhook_event.event_type = WebhookEvent.EventType.OTHER
                webhook_event.payload = event_data
                webhook_event.save(update_fields=["event_type", "payload"])
                result = {"success": True, "message": f"Unhandled Flutterwave event {event_type}", "data": data}

            return result
        except Exception as exc:
            logger.exception("Error processing Flutterwave webhook for reference %s: %s", tx_ref, exc)
            return {"success": False, "error": str(exc), "data": {}}

    # Flutterwave event handlers
    @staticmethod
    @transaction.atomic
    def _handle_successful_flutterwave_charge(data: Dict[str, Any], webhook_event: WebhookEvent) -> Dict[str, Any]:
        # Flutterwave can send tx_ref, flw_ref, or reference
        tx_ref = (
            data.get("tx_ref")
            or data.get("txRef")
            or data.get("flw_ref")
            or data.get("flwRef")
            or data.get("reference")
            or data.get("orderRef")
        )


        if not tx_ref:
            logger.error("No reference found in Flutterwave webhook: %s", data)
            return {"success": False, "error": "Missing transaction reference", "data": {}}

        amount = Decimal(str(data.get("amount", 0)))

        try:
            payment_txn = PaymentTransaction.objects.select_for_update().get(
                gateway_reference=tx_ref,
                transaction_type=PaymentTransaction.TransactionType.FUNDING,
            )
        except PaymentTransaction.DoesNotExist:
            logger.warning("PaymentTransaction not found for Flutterwave reference %s", tx_ref)
            return {"success": False, "error": "PaymentTransaction not found", "data": {}}

        # If already processed, exit early
        if payment_txn.status == PaymentTransaction.Status.SUCCESS:
            webhook_event.processed = True
            webhook_event.save(update_fields=["processed"])
            return {"success": True, "message": "Already processed", "data": {}}

        # Mark transaction as success
        payment_txn.status = PaymentTransaction.Status.SUCCESS
        payment_txn.completed_at = timezone.now()
        payment_txn.gateway_response = data
        payment_txn.save(update_fields=["status", "completed_at", "gateway_response"])

        # Credit wallet
        from wallets.services import WalletService
        WalletService.credit_wallet(
            user=payment_txn.user,
            amount=amount,
            category="funding",
            description=f"Wallet funding via Flutterwave (Ref: {tx_ref})",
            reference=payment_txn.internal_reference,
            payment_transaction=payment_txn,
        )

        # Mark webhook processed
        webhook_event.processed = True
        webhook_event.processed_at = timezone.now()
        webhook_event.payload = data
        webhook_event.save(update_fields=["processed", "processed_at", "payload"])

        return {"success": True, "message": "Wallet funded successfully", "data": {"reference": tx_ref}}

    @staticmethod
    def _handle_successful_flutterwave_transfer(data: Dict[str, Any], webhook_event: WebhookEvent) -> Dict[str, Any]:
        """Handle successful Flutterwave withdrawal transfer webhook."""
        reference = data.get("reference")
        try:
            with transaction.atomic():
                payment_txn = (
                    PaymentTransaction.objects.select_for_update()
                    .get(gateway_reference=reference, transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL)
                )

                if payment_txn.status == PaymentTransaction.Status.PENDING:
                    payment_txn.status = PaymentTransaction.Status.SUCCESS
                    payment_txn.completed_at = timezone.now()
                    payment_txn.gateway_response = data
                    payment_txn.save(update_fields=["status", "completed_at", "gateway_response"])

                    # Mark any matching WithdrawalRequest as approved (if present)
                    from wallets.models import WithdrawalRequest

                    withdrawal = WithdrawalRequest.objects.filter(gateway_reference=reference).first()
                    if withdrawal:
                        withdrawal.status = "approved"
                        withdrawal.processed_at = withdrawal.processed_at or timezone.now()
                        withdrawal.gateway_response = data
                        withdrawal.save(update_fields=["status", "processed_at", "gateway_response"])

                    webhook_event.processed = True
                    webhook_event.processed_at = timezone.now()
                    webhook_event.payload = data
                    webhook_event.save(update_fields=["processed", "processed_at", "payload"])
                    return {"success": True, "message": "Transfer processed successfully", "data": {}}

                return {"success": True, "message": "Transfer already processed", "data": {}}
        except PaymentTransaction.DoesNotExist:
            logger.warning("Withdrawal transaction not found for Flutterwave reference %s", reference)
            return {"success": False, "error": "Withdrawal transaction not found", "data": {}}

    @staticmethod
    def _handle_failed_flutterwave_transfer(data: Dict[str, Any], webhook_event: WebhookEvent) -> Dict[str, Any]:
        """Handle failed Flutterwave withdrawal webhook; refund user."""
        reference = data.get("reference")
        from wallets.services import WalletService
        from wallets.models import WithdrawalRequest

        try:
            with transaction.atomic():
                payment_txn = (
                    PaymentTransaction.objects.select_for_update()
                    .get(gateway_reference=reference, transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL)
                )

                if payment_txn.status == PaymentTransaction.Status.PENDING:
                    payment_txn.status = PaymentTransaction.Status.FAILED
                    payment_txn.gateway_response = data
                    payment_txn.save(update_fields=["status", "gateway_response"])

                    # Refund the user's wallet
                    WalletService.credit_wallet(
                        user=payment_txn.user,
                        amount=payment_txn.amount,
                        category="withdrawal_refund",
                        description=f"Refund for failed Flutterwave withdrawal (Ref: {reference})",
                        reference=payment_txn.internal_reference,
                        payment_transaction=payment_txn,
                    )

                    withdrawal = WithdrawalRequest.objects.filter(gateway_reference=reference).first()
                    if withdrawal:
                        withdrawal.status = "rejected"
                        withdrawal.processed_at = timezone.now()
                        withdrawal.gateway_response = data
                        withdrawal.save(update_fields=["status", "processed_at", "gateway_response"])

                    webhook_event.processed = True
                    webhook_event.processed_at = timezone.now()
                    webhook_event.payload = data
                    webhook_event.save(update_fields=["processed", "processed_at", "payload"])
                    return {"success": True, "message": "Failed transfer processed (refund issued)", "data": {}}

                return {"success": True, "message": "Failed transfer already processed", "data": {}}
        except PaymentTransaction.DoesNotExist:
            logger.warning("Withdrawal transaction not found for failed Flutterwave transfer reference %s", reference)
            return {"success": False, "error": "Withdrawal transaction not found", "data": {}}


class FlutterwaveService:
    """Service class for Flutterwave API integration.

    Methods return a consistent structure:
        {"success": bool, "data": {...}, "error": "message"}
    """

    def __init__(self):
        self.secret_key = settings.FLUTTERWAVE_SECRET_KEY
        self.public_key = getattr(settings, "FLUTTERWAVE_PUBLIC_KEY", None)
        self.base_url = "https://api.flutterwave.com/v3"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        })

    # ------------------------
    # Helpers
    # ------------------------
    def _get_gateway(self):
        try:
            return PaymentGateway.objects.get(name__iexact="flutterwave")
        except PaymentGateway.DoesNotExist:
            logger.error("Flutterwave PaymentGateway not configured in DB")
            return None

    # ------------------------
    # Initialize funding (payment)
    # ------------------------
    def initialize_payment(self, user, amount, currency="NGN", callback_url=None):
        """
        Initialize a payment transaction with Flutterwave.

        Returns:
            {"success": bool, "data": {...}, "error": str}
        """
        try:
            gateway = self._get_gateway()
            if not gateway:
                return {"success": False, "data": {}, "error": "Payment gateway not configured"}

            # Normalize amount to Decimal
            try:
                amount_dec = Decimal(amount)
            except (InvalidOperation, TypeError):
                return {"success": False, "data": {}, "error": "Invalid amount"}

            with transaction.atomic():
                # Create local pending PaymentTransaction
                payment_transaction = PaymentTransaction.objects.create(
                    user=user,
                    gateway=gateway,
                    transaction_type=PaymentTransaction.TransactionType.FUNDING,
                    amount=amount_dec,
                    currency=currency,
                    gateway_reference=f"FLW_{timezone.now().strftime('%Y%m%d%H%M%S')}_{str(user.id)[:8]}",
                    status=PaymentTransaction.Status.PENDING,
                )

                url = f"{self.base_url}/payments"
                payload = {
                    "tx_ref": payment_transaction.gateway_reference,
                    "amount": str(amount_dec),  # Flutterwave expects string
                    "currency": currency,
                    "redirect_url": callback_url or "https://example.com/callback",
                    "payment_options": "card,banktransfer,ussd",
                    "customer": {
                        "email": user.email,
                        "phonenumber": getattr(user, 'phone', ''),
                        "name": f"{user.first_name} {user.last_name}".strip() or getattr(user, 'username', str(user.id)),
                    },
                    "customizations": {
                        "title": "Wallet Funding",
                        "description": "Fund your wallet",
                        "logo": "https://yourapp.com/logo.png",  # Update with your logo
                    },
                    "meta": {
                        "user_id": str(user.id),
                        "transaction_id": str(payment_transaction.id),
                        "purpose": "wallet_funding",
                        "internal_reference": payment_transaction.internal_reference,
                    },
                }

                resp = self.session.post(url, json=payload, timeout=HTTP_TIMEOUT)
                resp_data = _safe_json(resp)

                if _ok_resp(resp) and resp_data.get("status") == "success":
                    pay_data = resp_data.get("data", {})
                    
                    # Check for payment link
                    if "link" not in pay_data:
                        payment_transaction.status = PaymentTransaction.Status.FAILED
                        payment_transaction.gateway_response = resp_data
                        payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])
                        err = "Missing payment link from gateway"
                        logger.error(err + " - resp: %s", resp_data)
                        return {"success": False, "data": resp_data, "error": err}

                    # Persist FlutterwaveTransaction
                    FlutterwaveTransaction.objects.create(
                        transaction=payment_transaction,
                        payment_link=pay_data.get("link"),
                        flutterwave_reference=payment_transaction.gateway_reference,
                    )

                    payment_transaction.gateway_response = resp_data
                    payment_transaction.save(update_fields=["gateway_response", "updated_at"])

                    return {
                        "success": True,
                        "data": {
                            "transaction_id": str(payment_transaction.id),
                            "internal_reference": payment_transaction.internal_reference,
                            "gateway_reference": payment_transaction.gateway_reference,
                            "payment_link": pay_data.get("link"),
                            "raw": resp_data,
                        },
                        "error": None,
                    }

                # Failure path: mark txn failed
                payment_transaction.status = PaymentTransaction.Status.FAILED
                payment_transaction.gateway_response = resp_data
                payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])

                err_msg = resp_data.get("message") or "Payment initialization failed"
                logger.info("Flutterwave init failed: %s", err_msg)
                return {"success": False, "data": resp_data, "error": err_msg}

        except requests.RequestException as exc:
            logger.exception("HTTP error during payment initialization: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error in initialize_payment: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Verify payment status
    # ------------------------
    def verify_payment(self, transaction_id: str) -> Dict[str, Any]:
        """
        Verify a payment with Flutterwave using transaction ID.
        Returns {"success": bool, "data": {...}, "error": str}
        """
        try:
            url = f"{self.base_url}/transactions/{transaction_id}/verify"
            resp = self.session.get(url, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)

            ok = _ok_resp(resp) and resp_data.get("status") == "success"
            return {"success": ok, "data": resp_data, "error": None if ok else resp_data.get("message", "Verification failed")}
        except requests.RequestException as exc:
            logger.exception("HTTP error during payment verification: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error during payment verification: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    def verify_payment_by_reference(self, tx_ref: str) -> Dict[str, Any]:
        """
        Verify a payment with Flutterwave using transaction reference.
        Returns {"success": bool, "data": {...}, "error": str}
        """
        try:
            url = f"{self.base_url}/transactions/verify_by_reference"
            params = {"tx_ref": tx_ref}
            resp = self.session.get(url, params=params, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)

            ok = _ok_resp(resp) and resp_data.get("status") == "success"
            return {"success": ok, "data": resp_data, "error": None if ok else resp_data.get("message", "Verification failed")}
        except requests.RequestException as exc:
            logger.exception("HTTP error during payment verification: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error during payment verification: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Create beneficiary (for transfers)
    # ------------------------
    def create_beneficiary(self, user, bank_code: str, account_number: str) -> Dict[str, Any]:
        """Create a beneficiary for transfers (withdrawals)."""
        try:
            url = f"{self.base_url}/beneficiaries"
            payload = {
                "account_bank": bank_code,
                "account_number": account_number,
                "beneficiary_name": f"{user.first_name} {user.last_name}".strip() or getattr(user, "username", str(user.id)),
            }
            resp = self.session.post(url, json=payload, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)
            ok = _ok_resp(resp) and resp_data.get("status") == "success"

            if ok:
                return {"success": True, "data": resp_data.get("data", {}), "error": None}
            return {"success": False, "data": resp_data, "error": resp_data.get("message", "Failed to create beneficiary")}
        except requests.RequestException as exc:
            logger.exception("HTTP error creating beneficiary: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error creating beneficiary: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Initiate transfer (withdrawal)
    # ------------------------
    def initiate_transfer(self, user, amount, bank_code: str, account_number: str, narration: str = "Wallet withdrawal") -> Dict[str, Any]:
        """
        Initiate a transfer (withdrawal).
        Creates a PENDING PaymentTransaction and FlutterwaveTransaction.
        """
        try:
            gateway = self._get_gateway()
            if not gateway:
                return {"success": False, "data": {}, "error": "Payment gateway not configured"}

            try:
                amount_dec = Decimal(amount)
            except (InvalidOperation, TypeError):
                return {"success": False, "data": {}, "error": "Invalid amount"}

            with transaction.atomic():
                payment_transaction = PaymentTransaction.objects.create(
                    user=user,
                    gateway=gateway,
                    transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
                    amount=amount_dec,
                    currency="NGN",
                    gateway_reference=f"FLW_WD_{timezone.now().strftime('%Y%m%d%H%M%S')}_{str(user.id)[:8]}",
                    status=PaymentTransaction.Status.PENDING,
                )

                url = f"{self.base_url}/transfers"
                payload = {
                    "account_bank": bank_code,
                    "account_number": account_number,
                    "amount": int(amount_dec),  # Flutterwave expects integer for NGN
                    "currency": "NGN",
                    "reference": payment_transaction.gateway_reference,
                    "narration": narration,
                    "callback_url": "https://cc-marketers.onrender.com/payments/webhooks/flutterwave/",  
                    "debit_currency": "NGN",
                }

                resp = self.session.post(url, json=payload, timeout=HTTP_TIMEOUT)
                resp_data = _safe_json(resp)

                if _ok_resp(resp) and resp_data.get("status") == "success":
                    pay_data = resp_data.get("data", {})
                    FlutterwaveTransaction.objects.create(
                        transaction=payment_transaction,
                        flutterwave_reference=payment_transaction.gateway_reference,
                        transfer_id=str(pay_data.get("id", "")),
                        bank_code=bank_code,
                        account_number=account_number,
                    )

                    payment_transaction.gateway_response = resp_data
                    payment_transaction.save(update_fields=["gateway_response", "updated_at"])
                    return {
                        "success": True,
                        "data": {
                            "transaction_id": str(payment_transaction.id),
                            "internal_reference": payment_transaction.internal_reference,
                            "gateway_reference": payment_transaction.gateway_reference,
                            "transfer_id": pay_data.get("id"),
                            "status": pay_data.get("status"),
                            "raw": resp_data,
                        },
                        "error": None,
                    }

                # Mark as failed and persist response
                payment_transaction.status = PaymentTransaction.Status.FAILED
                payment_transaction.gateway_response = resp_data
                payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])

                err = resp_data.get("message") or "Transfer initiation failed"
                logger.info("Flutterwave transfer failed: %s", err)
                return {"success": False, "data": resp_data, "error": err}

        except requests.RequestException as exc:
            logger.exception("HTTP error initiating transfer: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error initiating transfer: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

    # ------------------------
    # Get banks
    # ------------------------
    def get_banks(self, country: str = "NG") -> Dict[str, Any]:
        """Return list of banks from Flutterwave."""
        try:
            url = f"{self.base_url}/banks/{country}"
            resp = self.session.get(url, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)
            ok = _ok_resp(resp) and resp_data.get("status") == "success"

            if ok and isinstance(resp_data.get("data", None), list):
                return {"success": True, "data": resp_data.get("data", []), "error": None}
            return {"success": False, "data": [], "error": resp_data.get("message", "Failed to fetch banks")}
        except requests.RequestException as exc:
            logger.exception("HTTP error fetching banks: %s", exc)
            return {"success": False, "data": [], "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error fetching banks: %s", exc)
            return {"success": False, "data": [], "error": str(exc)}

    # ------------------------
    # Resolve account number
    # ------------------------
    def resolve_account_number(self, account_number: str, bank_code: str) -> Dict[str, Any]:
        """Resolve an account number to an account name."""
        try:
            url = f"{self.base_url}/accounts/resolve"
            payload = {
                "account_number": account_number,
                "account_bank": bank_code
            }
            resp = self.session.post(url, json=payload, timeout=HTTP_TIMEOUT)
            resp_data = _safe_json(resp)
            ok = _ok_resp(resp) and resp_data.get("status") == "success"

            if ok:
                return {"success": True, "data": resp_data.get("data", {}), "error": None}
            return {"success": False, "data": {}, "error": resp_data.get("message", "Resolve failed")}
        except requests.RequestException as exc:
            logger.exception("HTTP error resolving account: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error resolving account: %s", exc)
            return {"success": False, "data": {}, "error": str(exc)}

