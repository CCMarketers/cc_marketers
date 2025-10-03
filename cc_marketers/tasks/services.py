# tasks/services/task_wallet_service.py
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model

from wallets.models import EscrowTransaction
from .models import TaskWallet, TaskWalletTransaction
from wallets.services import WalletService  # main wallet service

User = get_user_model()


def get_company_user():
    """
    Return or create the system/company user for escrow operations.
    """
    user, _ = User.objects.get_or_create(
        username=settings.COMPANY_SYSTEM_USERNAME,
        defaults={
            "email": f"{settings.COMPANY_SYSTEM_USERNAME}@gmail.com",
            "role": getattr(User, 'ADMIN', None),
            "is_staff": True,
            "is_superuser": True,
        },
    )
    return user


class TaskWalletService:
    """
    Service layer for handling all TaskWallet operations.
    """

    # -------------------------------
    # Utility helpers
    # -------------------------------
    @staticmethod
    def split_payment(amount, company_rate=Decimal("0.20")):
        """
        Split escrow amount between worker and company.
        Returns (member_amount, company_cut)
        """
        amount = Decimal(amount)
        company_cut = (amount * company_rate).quantize(Decimal("0.01"))
        member_amount = amount - company_cut
        return member_amount, company_cut

    @staticmethod
    def get_or_create_wallet(user):
        """
        Get or create a TaskWallet for a user.
        """
        wallet, _ = TaskWallet.objects.get_or_create(user=user)
        return wallet

    # -------------------------------
    # Balance Operations
    # -------------------------------
    @staticmethod
    @transaction.atomic
    def credit_wallet(user, amount, category="admin_adjustment", description="", reference=None):
        """
        Credit TaskWallet and log transaction.
        """
        amount = Decimal(amount)
        wallet = TaskWalletService.get_or_create_wallet(user)

        before = wallet.balance
        wallet.balance += amount
        wallet.save(update_fields=['balance'])

        TaskWalletTransaction.objects.create(
            user=user,
            transaction_type="credit",
            category=category,
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            description=description,
            reference=reference,
        )
        return wallet

    @staticmethod
    @transaction.atomic
    def debit_wallet(user, amount, category="task_posting", description="", reference=None):
        """
        Debit TaskWallet and log transaction.
        """
        amount = Decimal(amount)
        wallet = TaskWalletService.get_or_create_wallet(user)
        if wallet.balance < amount:
            raise ValueError("Insufficient Task Wallet balance")

        before = wallet.balance
        wallet.balance -= amount
        wallet.save(update_fields=['balance'])

        TaskWalletTransaction.objects.create(
            user=user,
            transaction_type="debit",
            category=category,
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            description=description,
            reference=reference,
        )
        return wallet

    # -------------------------------
    # Transfers
    # -------------------------------
    @staticmethod
    @transaction.atomic
    def transfer_from_main_wallet(user, amount):
        """
        Move funds from Main Wallet into TaskWallet.
        """
        amount = Decimal(amount)
        # debit from main wallet
        debit_txn = WalletService.debit_wallet(
            user=user,
            amount=amount,
            category="task_wallet_topup",
            description="Top-up Task Wallet",
        )

        # credit task wallet
        return TaskWalletService.credit_wallet(
            user=user,
            amount=amount,
            category="topup_from_main",
            description="Top-up from Main Wallet",
            reference=getattr(debit_txn, "reference", None),
        )

    # -------------------------------
    # Escrow
    # -------------------------------
    @staticmethod
    @transaction.atomic
    def create_task_escrow(advertiser, task, amount):
        """
        Lock advertiser funds in escrow when task is created.
        """
        amount = Decimal(amount)
        wallet = TaskWalletService.get_or_create_wallet(advertiser)

        if wallet.balance < amount:
            raise ValueError("Insufficient Task Wallet balance")

        before = wallet.balance
        wallet.balance -= amount
        wallet.save(update_fields=['balance'])

        txn = TaskWalletTransaction.objects.create(
            user=advertiser,
            transaction_type="debit",
            category="task_posting",
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            description=f"Escrow for task: {task.title}",
        )

        escrow = EscrowTransaction.objects.create(
            task=task,
            advertiser=advertiser,
            amount_usd=amount,
            taskwallet_transaction=txn,
            status="locked",
        )
        return escrow

    @staticmethod
    @transaction.atomic
    def release_task_escrow(escrow, member):
        """
        Release escrow to worker and company after approval.
        """
        if escrow.status != "locked":
            raise ValueError("Escrow already released or refunded")

        # Split payment
        member_amount, company_cut = TaskWalletService.split_payment(escrow.amount_usd)

        # Pay worker
        WalletService.credit_wallet(
            user=member,
            amount=member_amount,
            description=f"Payment for task: {escrow.task.title}",
            category="task_payment",
        )

        # Pay company
        WalletService.credit_wallet(
            user=get_company_user(),
            amount=company_cut,
            description=f"Company cut for task: {escrow.task.title}",
            category="company_cut",
        )

        escrow.status = "released"
        escrow.released_at = timezone.now()
        escrow.save(update_fields=['status', 'released_at'])

        # Update transaction status if applicable
        if hasattr(escrow, "taskwallet_transaction") and hasattr(escrow.taskwallet_transaction, "status"):
            escrow.taskwallet_transaction.status = "success"
            escrow.taskwallet_transaction.save(update_fields=['status'])

        return escrow

    @staticmethod
    @transaction.atomic
    def refund_task_escrow(escrow):
        """
        Refund advertiser when dispute resolves in their favor.
        """
        if escrow.status != "locked":
            raise ValueError("Escrow already released or refunded")

        wallet = TaskWalletService.get_or_create_wallet(escrow.advertiser)

        before = wallet.balance
        wallet.balance += escrow.amount
        wallet.save(update_fields=['balance'])

        TaskWalletTransaction.objects.create(
            user=escrow.advertiser,
            transaction_type="credit",
            category="task_posting",
            amount=escrow.amount,
            balance_before=before,
            balance_after=wallet.balance,
            description=f"Refund for task: {escrow.task.title}",
        )

        escrow.status = "refunded"
        escrow.released_at = timezone.now()
        escrow.save(update_fields=['status', 'released_at'])

        if hasattr(escrow, "taskwallet_transaction") and hasattr(escrow.taskwallet_transaction, "status"):
            escrow.taskwallet_transaction.status = "failed"
            escrow.taskwallet_transaction.save(update_fields=['status'])

        return escrow
