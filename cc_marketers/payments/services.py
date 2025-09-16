# payments/services.py
import requests
import hmac
import hashlib
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import PaymentTransaction, PaystackTransaction, PaymentGateway, WebhookEvent


class PaystackService:
    """Service class for Paystack API integration"""

    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = "https://api.paystack.co"
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

    # ---------- Customer Funding ----------
    def initialize_payment(self, user, amount, currency='NGN', callback_url=None):
        """
        Initialize a payment transaction with Paystack.
        Creates PaymentTransaction + PaystackTransaction (pending) on success.
        Returns a consistent shape: {"success": bool, "data": {...}}.
        """
        try:
            gateway = PaymentGateway.objects.get(name='paystack')

            with transaction.atomic():
                # 1. Create local payment record (pending)
                payment_transaction = PaymentTransaction.objects.create(
                    user=user,
                    gateway=gateway,
                    transaction_type=PaymentTransaction.TransactionType.FUNDING,
                    amount=Decimal(amount),
                    currency=currency,
                    gateway_reference=f"PS_{timezone.now().strftime('%Y%m%d%H%M%S')}_{user.id}",
                    status=PaymentTransaction.Status.PENDING,
                )

                # 2. Build request payload
                url = f"{self.base_url}/transaction/initialize"
                data = {
                    "email": user.email,
                    "amount": int(Decimal(amount) * 100),  # Convert to kobo
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

                # 3. Send to Paystack
                response = requests.post(url, json=data, headers=self.headers, timeout=15)
                response_data = response.json()

                # 4. Handle success
                if response.status_code == 200 and response_data.get("status") is True:
                    paystack_data = response_data.get("data", {})

                    # Defensive check – must contain authorization_url
                    if "authorization_url" not in paystack_data:
                        raise ValueError("No authorization_url returned from Paystack")

                    PaystackTransaction.objects.create(
                        transaction=payment_transaction,
                        authorization_url=paystack_data["authorization_url"],
                        access_code=paystack_data.get("access_code"),
                        paystack_reference=paystack_data.get("reference"),
                    )

                    # Save gateway response
                    payment_transaction.gateway_response = response_data
                    payment_transaction.save(update_fields=["gateway_response", "updated_at"])

                    return {
                        "success": True,
                        "data": {
                            "transaction_id": str(payment_transaction.id),
                            "internal_reference": payment_transaction.internal_reference,
                            "gateway_reference": payment_transaction.gateway_reference,
                            "authorization_url": paystack_data["authorization_url"],
                            "access_code": paystack_data.get("access_code"),
                            "reference": paystack_data.get("reference"),
                            "raw": response_data,
                        },
                    }

                # 5. Failure path
                payment_transaction.status = PaymentTransaction.Status.FAILED
                payment_transaction.gateway_response = response_data
                payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])

                return {
                    "success": False,
                    "error": response_data.get("message", "Payment initialization failed"),
                    "data": {"raw": response_data},
                }

        except Exception as e:
            return {"success": False, "error": str(e), "data": {}}

    def verify_payment(self, reference):
        """Verify a payment with Paystack — consistent return."""
        try:
            url = f"{self.base_url}/transaction/verify/{reference}"
            response = requests.get(url, headers=self.headers)
            data = response.json() if response.content else {}

            return {
                "success": response.status_code == 200 and data.get("status", False),
                "data": data
            }
        except Exception as e:
            return {"success": False, "error": str(e), "data": {}}

    # ---------- Payouts / Withdrawals ----------

    def create_transfer_recipient(self, user, bank_code, account_number):
        """Create a transfer recipient for withdrawals — consistent return."""
        try:
            url = f"{self.base_url}/transferrecipient"
            data = {
                "type": "nuban",
                "name": f"{user.first_name} {user.last_name}".strip() or user.username,
                "account_number": account_number,
                "bank_code": bank_code,
                "currency": "NGN",
                "metadata": {"user_id": str(user.id)}
            }
            response = requests.post(url, json=data, headers=self.headers)
            response_data = response.json()
            ok = response.status_code in (200, 201) and response_data.get("status", False)

            return {
                "success": ok,
                "data": response_data if ok else {},
                **({} if ok else {"error": response_data.get("message", "Failed to create recipient")})
            }
        except Exception as e:
            return {"success": False, "error": str(e), "data": {}}

    def initiate_transfer(self, user, amount, recipient_code, reason="Wallet withdrawal"):
        """
        Initiate a transfer to user's bank account.
        Creates PaymentTransaction + PaystackTransaction (pending) when API acknowledges.
        Returns a consistent shape.
        """
        try:
            gateway = PaymentGateway.objects.get(name='paystack')

            with transaction.atomic():
                # Create withdrawal transaction (PENDING) first
                payment_transaction = PaymentTransaction.objects.create(
                    user=user,
                    gateway=gateway,
                    transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
                    amount=Decimal(amount),
                    currency="NGN",
                    gateway_reference=f"WD_{timezone.now().strftime('%Y%m%d%H%M%S')}_{user.id}",
                    status=PaymentTransaction.Status.PENDING,
                )

                url = f"{self.base_url}/transfer"
                data = {
                    "source": "balance",
                    "amount": int(Decimal(amount) * 100),  # kobo
                    "recipient": recipient_code,
                    "reason": reason,
                    "reference": payment_transaction.gateway_reference,
                }

                response = requests.post(url, json=data, headers=self.headers, timeout=15)
                response_data = response.json()

                if response.status_code == 200 and response_data.get("status") is True:
                    paystack_data = response_data["data"]

                    # Save Paystack-specific transaction
                    PaystackTransaction.objects.create(
                        transaction=payment_transaction,
                        paystack_reference=paystack_data.get("reference"),
                        transfer_code=paystack_data.get("transfer_code"),
                    )

                    # Attach gateway response for auditing
                    payment_transaction.gateway_response = response_data
                    payment_transaction.save(update_fields=["gateway_response", "updated_at"])

                    return {
                        "success": True,
                        "data": {
                            "transaction_id": str(payment_transaction.id),
                            "internal_reference": payment_transaction.internal_reference,
                            "gateway_reference": payment_transaction.gateway_reference,
                            "paystack_reference": paystack_data.get("reference"),
                            "transfer_code": paystack_data.get("transfer_code"),
                            "status": paystack_data.get("status"),
                            "raw": response_data,
                        },
                    }

                # Failure: mark txn failed
                payment_transaction.status = PaymentTransaction.Status.FAILED
                payment_transaction.gateway_response = response_data
                payment_transaction.save(update_fields=["status", "gateway_response", "updated_at"])

                return {
                    "success": False,
                    "error": response_data.get("message", "Transfer failed"),
                    "data": {"raw": response_data},
                }

        except Exception as e:
            return {"success": False, "error": str(e), "data": {}}

    def get_banks(self):
        """Get list of Nigerian banks from Paystack — consistent return."""
        try:
            url = f"{self.base_url}/bank"
            response = requests.get(url, headers=self.headers)
            data = response.json() if response.content else {}
            ok = response.status_code == 200
            return {"success": ok, "data": data.get("data", []) if ok else [], **({} if ok else {"error": "Failed to fetch banks"})}
        except Exception as e:
            return {"success": False, "error": str(e), "data": []}

    def resolve_account_number(self, account_number, bank_code):
        """Resolve account number to get account name — consistent return."""
        try:
            url = f"{self.base_url}/bank/resolve"
            params = {"account_number": account_number, "bank_code": bank_code}
            response = requests.get(url, params=params, headers=self.headers)
            data = response.json() if response.content else {}
            ok = response.status_code == 200 and data.get("status", False)
            return {"success": ok, "data": data if ok else {}, **({} if ok else {"error": data.get("message", "Resolve failed")})}
        except Exception as e:
            return {"success": False, "error": str(e), "data": {}}


class WebhookService:
    """Service for handling payment webhooks"""

    @staticmethod
    def verify_paystack_signature(payload, signature):
        """Verify Paystack webhook signature"""
        secret_key = settings.PAYSTACK_SECRET_KEY
        computed_signature = hmac.new(
            secret_key.encode("utf-8"),
            payload,
            hashlib.sha512,
        ).hexdigest()

        return hmac.compare_digest(computed_signature, signature)

    @staticmethod
    def process_paystack_webhook(event_data):
        """Process Paystack webhook events"""
        event_type = event_data.get("event")
        data = event_data.get("data", {})
        reference = data.get("reference")

        if not reference:
            return {"success": False, "error": "No reference found"}

        gateway = PaymentGateway.objects.get(name='paystack')
        webhook_event, _ = WebhookEvent.objects.get_or_create(
            gateway=gateway,
            reference=reference,
            defaults={
                "event_type": event_type,
                "payload": event_data,
            },
        )

        if webhook_event.processed:
            return {"success": True, "message": "Duplicate event ignored"}

        try:
            if event_type == "charge.success":
                result = WebhookService._handle_successful_charge(data, webhook_event)
            elif event_type == "transfer.success":
                result = WebhookService._handle_successful_transfer(data, webhook_event)
            elif event_type in ["transfer.failed", "transfer.reversed"]:
                result = WebhookService._handle_failed_transfer(data, webhook_event)
            else:
                webhook_event.event_type = WebhookEvent.EventType.OTHER
                webhook_event.save(update_fields=["event_type"])
                result = {"success": True, "message": "Unhandled event recorded"}

            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ----------------- Event Handlers -----------------

    @staticmethod
    def _handle_successful_charge(data, webhook_event):
        """Handle successful charge webhook (funding)"""
        reference = data.get("reference")
        amount = Decimal(data.get("amount", 0)) / 100  # Convert from kobo
        from wallets.services import WalletService

        try:
            with transaction.atomic():
                payment_txn = PaymentTransaction.objects.select_for_update().get(
                    gateway_reference=reference,
                    transaction_type=PaymentTransaction.TransactionType.FUNDING,
                )

                if payment_txn.status == PaymentTransaction.Status.PENDING:
                    payment_txn.status = PaymentTransaction.Status.SUCCESS
                    payment_txn.completed_at = timezone.now()
                    payment_txn.gateway_response = data
                    payment_txn.save(update_fields=["status", "completed_at", "gateway_response", "updated_at"])

                    # Credit wallet and LINK to payment transaction
                    WalletService.credit_wallet(
                        user=payment_txn.user,
                        amount=amount,
                        category="funding",
                        description=f"Wallet funding via Paystack (Ref: {reference})",
                        reference=payment_txn.internal_reference,
                        payment_transaction=payment_txn,
                    )

                    webhook_event.processed = True
                    webhook_event.processed_at = timezone.now()
                    webhook_event.save(update_fields=["processed", "processed_at"])

                    return {"success": True, "message": "Charge processed successfully"}

                return {"success": True, "message": "Charge already processed"}

        except PaymentTransaction.DoesNotExist:
            return {"success": False, "error": "Funding transaction not found"}

    @staticmethod
    def _handle_successful_transfer(data, webhook_event):
        """Handle successful withdrawal transfer webhook"""
        reference = data.get("reference")

        try:
            with transaction.atomic():
                payment_txn = PaymentTransaction.objects.select_for_update().get(
                    gateway_reference=reference,
                    transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
                )

                if payment_txn.status == PaymentTransaction.Status.PENDING:
                    payment_txn.status = PaymentTransaction.Status.SUCCESS
                    payment_txn.completed_at = timezone.now()
                    payment_txn.gateway_response = data
                    payment_txn.save(update_fields=["status", "completed_at", "gateway_response", "updated_at"])

                    # The admin flow already debited wallet and created WithdrawalRequest
                    # We only need to mark the related WithdrawalRequest as approved if present.
                    from wallets.models import WithdrawalRequest
                    withdrawal = WithdrawalRequest.objects.filter(gateway_reference=reference).first()
                    if withdrawal:
                        withdrawal.status = "approved"  # idempotent
                        withdrawal.processed_at = withdrawal.processed_at or timezone.now()
                        withdrawal.gateway_response = data
                        withdrawal.save(update_fields=["status", "processed_at", "gateway_response"])

                    webhook_event.processed = True
                    webhook_event.processed_at = timezone.now()
                    webhook_event.save(update_fields=["processed", "processed_at"])

                    return {"success": True, "message": "Transfer processed successfully"}

                return {"success": True, "message": "Transfer already processed"}

        except PaymentTransaction.DoesNotExist:
            return {"success": False, "error": "Withdrawal transaction not found"}

    @staticmethod
    def _handle_failed_transfer(data, webhook_event):
        """Handle failed/reversed withdrawal webhook"""
        reference = data.get("reference")
        from wallets.services import WalletService
        from wallets.models import WithdrawalRequest

        try:
            with transaction.atomic():
                payment_txn = PaymentTransaction.objects.select_for_update().get(
                    gateway_reference=reference,
                    transaction_type=PaymentTransaction.TransactionType.WITHDRAWAL,
                )

                if payment_txn.status == PaymentTransaction.Status.PENDING:
                    payment_txn.status = PaymentTransaction.Status.FAILED
                    payment_txn.gateway_response = data
                    payment_txn.save(update_fields=["status", "gateway_response", "updated_at"])

                    # Refund wallet (link back to the original payment transaction)
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
                    webhook_event.save(update_fields=["processed", "processed_at"])

                    return {"success": True, "message": "Failed transfer processed"}

                return {"success": True, "message": "Failed transfer already processed"}

        except PaymentTransaction.DoesNotExist:
            return {"success": False, "error": "Withdrawal transaction not found"}

