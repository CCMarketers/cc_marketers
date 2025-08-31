# wallets/services.py
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import uuid

from .models import Wallet, Transaction, EscrowTransaction, WithdrawalRequest
from referrals.models import ReferralEarning
from tasks.models import TaskWalletTransaction
from payments.models import PaymentTransaction, PaymentGateway
from payments.services import PaystackService


class WalletService:
    """Handle all wallet operations with proper double-entry bookkeeping"""

    @staticmethod
    def get_or_create_wallet(user):
        wallet, _ = Wallet.objects.get_or_create(user=user)
        return wallet

    @staticmethod
    @transaction.atomic
    def credit_wallet(user, amount, category, description="", reference=None, task=None, payment_transaction=None):
        wallet = WalletService.get_or_create_wallet(user)
        amount = Decimal(amount)

        txn = Transaction.objects.create(
            user=user,
            transaction_type='credit',
            category=category,
            amount=amount,
            balance_before=wallet.balance,
            balance_after=wallet.balance + amount,
            status='success',
            reference=reference or str(uuid.uuid4()),
            description=description,
            task=task,
            payment_transaction=payment_transaction,  # 👈 ensure linkage
        )

        wallet.balance += amount
        wallet.save(update_fields=["balance", "updated_at"])
        return txn

    @staticmethod
    @transaction.atomic
    def debit_wallet(user, amount, category, description="", reference=None, task=None, payment_transaction=None):
        wallet = WalletService.get_or_create_wallet(user)
        amount = Decimal(amount)

        available_balance = wallet.get_available_balance() if category == 'escrow' else wallet.balance
        if available_balance < amount:
            raise ValueError(f"Insufficient balance. Available: ${available_balance}, Required: ${amount}")

        txn = Transaction.objects.create(
            user=user,
            transaction_type='debit',
            category=category,
            amount=amount,
            balance_before=wallet.balance,
            balance_after=wallet.balance - amount,
            status='success',
            reference=reference or str(uuid.uuid4()),
            description=description,
            task=task,
            payment_transaction=payment_transaction,  # 👈 ensure linkage
        )

        wallet.balance -= amount
        wallet.save(update_fields=["balance", "updated_at"])
        return txn

    # ---------- Escrow (Task) ----------

    @staticmethod
    @transaction.atomic
    def create_task_escrow(user, task, amount):
        from tasks.services import TaskWalletService
        wallet = TaskWalletService.get_or_create_wallet(user)
        amount = Decimal(amount)

        if wallet.balance < amount:
            raise ValueError(f"Insufficient TaskWallet balance. Available: {wallet.balance}, Required: {amount}")

        before = wallet.balance
        wallet.balance -= amount
        wallet.save(update_fields=["balance", "updated_at"])

        txn = TaskWalletTransaction.objects.create(
            user=user,
            transaction_type="debit",
            category="task_posting",
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            description=f"Escrow for task: {task.title}",
        )

        escrow = EscrowTransaction.objects.create(
            task=task,
            advertiser=user,
            amount=amount,
            taskwallet_transaction=txn,
            status="locked",
        )
        return escrow

    @staticmethod
    @transaction.atomic
    def release_escrow_to_member(task, member):
        from django.conf import settings
        from django.contrib.auth import get_user_model

        User = get_user_model()

        escrow = EscrowTransaction.objects.select_for_update().get(task=task, status='locked')

        company_cut = (escrow.amount * Decimal("0.20")).quantize(Decimal("0.01"))
        member_amount = escrow.amount - company_cut

        company_user = User.objects.get(username=settings.COMPANY_SYSTEM_USERNAME)

        member_txn = WalletService.credit_wallet(
            user=member,
            amount=member_amount,
            category="task_earning",
            description=f"Payment for completed task: {task.title}",
            reference=f"TASK_PAYMENT_{task.id}",
            task=task,
        )

        WalletService.credit_wallet(
            user=company_user,
            amount=company_cut,
            category="platform_fee",
            description=f"20% platform fee for task: {task.title}",
            reference=f"FEE_TASK_{task.id}",
            task=task,
        )

        escrow.status = "released"
        escrow.released_at = timezone.now()
        escrow.save(update_fields=["status", "released_at"])
        escrow.taskwallet_transaction.status = "success"
        escrow.taskwallet_transaction.save(update_fields=["status"])

        return member_txn

    @staticmethod
    @transaction.atomic
    def refund_escrow_to_advertiser(task):
        escrow = EscrowTransaction.objects.select_for_update().get(task=task, status='locked')

        credit_txn = WalletService.credit_wallet(
            user=escrow.advertiser,
            amount=escrow.amount,
            category='refund',
            description=f"Refund for task: {task.title}",
            reference=f"REFUND_TASK_{task.id}",
            task=task
        )

        escrow.status = "refunded"
        escrow.released_at = timezone.now()
        escrow.save(update_fields=["status", "released_at"])
        escrow.taskwallet_transaction.status = "failed"
        escrow.taskwallet_transaction.save(update_fields=["status"])

        return credit_txn

    # ---------- Referral ----------

    @staticmethod
    @transaction.atomic
    def process_referral_bonus(referrer, referred, amount=Decimal('10.00')):
        credit_txn = WalletService.credit_wallet(
            user=referrer,
            amount=Decimal(amount),
            category='referral_bonus',
            description=f"Referral bonus for {referred.username}",
            reference=f"REFERRAL_{referred.id}"
        )

        referral = ReferralEarning.objects.create(
            referrer=referrer,
            referred=referred,
            amount=Decimal(amount),
            transaction=credit_txn
        )
        return referral

    # ---------- Withdrawals ----------

    @staticmethod
    @transaction.atomic
    def create_withdrawal_request(user, amount, withdrawal_method, account_details):
        wallet = WalletService.get_or_create_wallet(user)
        amount = Decimal(amount)

        if amount < Decimal("10.00"):
            raise ValueError("Minimum withdrawal amount is $10.")

        if wallet.balance < amount:
            raise ValueError(f"Insufficient balance. Available: ${wallet.balance}, Required: ${amount}")

        withdrawal = WithdrawalRequest.objects.create(
            user=user,
            amount=amount,
            withdrawal_method=withdrawal_method,
            account_number=account_details.get('account_number', ''),
            account_name=account_details.get('account_name', ''),
            bank_name=account_details.get('bank_name', ''),
            bank_code=account_details.get('bank_code', ''),
            status='pending'
        )
        return withdrawal

    @staticmethod
    @transaction.atomic
    def approve_withdrawal(withdrawal_id, admin_user):
        """
        Approve withdrawal request, create Paystack recipient, initiate transfer via Paystack,
        and DEBIT wallet linked to the created PaymentTransaction.
        We keep PaymentTransaction status PENDING; webhook will flip to SUCCESS/FAILED.
        """
        withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)

        if withdrawal.status != "pending":
            raise ValueError("Withdrawal request is not pending")

        # 1) Paystack recipient
        paystack = PaystackService()
        recipient_result = paystack.create_transfer_recipient(
            withdrawal.user, withdrawal.bank_code, withdrawal.account_number
        )
        if not recipient_result.get("success"):
            raise ValueError(recipient_result.get("error", "Failed to create Paystack transfer recipient"))

        recipient_code = recipient_result["data"]["data"]["recipient_code"]

        # 2) Initiate transfer (creates PaymentTransaction + PaystackTransaction)
        transfer_result = paystack.initiate_transfer(
            user=withdrawal.user,
            amount=withdrawal.amount,
            recipient_code=recipient_code,
            reason=f"Withdrawal {withdrawal.id}"
        )
        if not transfer_result.get("success"):
            # Do not debit; surface error
            raise ValueError(transfer_result.get("error", "Paystack transfer failed"))

        txn_id = transfer_result["data"]["transaction_id"]
        gateway_reference = transfer_result["data"]["reference"]
        transfer_code = transfer_result["data"]["transfer_code"]

        # Fetch created PaymentTransaction
        payment_txn = PaymentTransaction.objects.get(id=txn_id)

        # 3) Debit wallet (link to payment transaction)
        debit_txn = WalletService.debit_wallet(
            user=withdrawal.user,
            amount=withdrawal.amount,
            category="withdrawal",
            description=f"Withdrawal request #{withdrawal.id}",
            reference=payment_txn.internal_reference,
            payment_transaction=payment_txn,
        )

        # 4) Persist withdrawal bookkeeping
        withdrawal.status = "approved"            # admin approval; webhook will also mark/confirm
        withdrawal.processed_by = admin_user
        withdrawal.processed_at = timezone.now()
        withdrawal.transaction = debit_txn
        withdrawal.gateway_reference = gateway_reference
        withdrawal.gateway_response = transfer_result["data"]["raw"]
        withdrawal.save(update_fields=[
            "status", "processed_by", "processed_at",
            "transaction", "gateway_reference", "gateway_response"
        ])

        # Also ensure PaystackTransaction carries bank info
        pst = payment_txn.paystack_details
        pst.bank_code = withdrawal.bank_code
        pst.account_number = withdrawal.account_number
        pst.account_name = withdrawal.account_name
        pst.recipient_code = recipient_code  # ensure stored
        pst.transfer_code = transfer_code
        pst.save(update_fields=["bank_code", "account_number", "account_name", "recipient_code", "transfer_code"])

        return withdrawal

    @staticmethod
    @transaction.atomic
    def reject_withdrawal(withdrawal_id, admin_user, reason=""):
        withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)

        if withdrawal.status != 'pending':
            raise ValueError("Withdrawal request is not pending")

        withdrawal.status = 'rejected'
        withdrawal.processed_by = admin_user
        withdrawal.processed_at = timezone.now()
        withdrawal.admin_notes = reason
        withdrawal.save(update_fields=["status", "processed_by", "processed_at", "admin_notes"])
        return withdrawal

    # ---------- Funding entry point for UI ----------

    @staticmethod
    @transaction.atomic
    def fund_wallet(user, amount, gateway_name="paystack", metadata=None, callback_url=None):
        """
        Initialize a funding transaction. Delegates to PaystackService.initialize_payment.
        Returns the authorization_url (string) on success.
        """
        gateway = PaymentGateway.objects.get(name__iexact=gateway_name, is_active=True)

        if gateway.name.lower() != "paystack":
            raise ValueError("Unsupported payment gateway")

        paystack = PaystackService()
        init_result = paystack.initialize_payment(user, Decimal(amount), currency='NGN', callback_url=callback_url)

        if not init_result.get("success"):
            raise ValueError(init_result.get("error", "Payment initialization failed"))

        # (Optional) you can stash metadata onto the created PaymentTransaction
        try:
            pt_id = init_result["data"]["transaction_id"]
            pt = PaymentTransaction.objects.get(id=pt_id)
            if metadata:
                pt.metadata = {**(pt.metadata or {}), **metadata}
                pt.save(update_fields=["metadata", "updated_at"])
        except Exception:
            pass  # non-fatal

        return init_result["data"]["authorization_url"]
