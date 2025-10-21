# tasks/services/task_wallet_service.py
from decimal import Decimal
import logging
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model

from wallets.models import EscrowTransaction
from .models import TaskWallet, TaskWalletTransaction
from wallets.services import WalletService  # main wallet service
logger = logging.getLogger(__name__)

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


    @staticmethod
    @transaction.atomic
    def transfer_to_main_wallet(user, amount):
        """
        Move funds from TaskWallet into Main Wallet (for withdrawal).
        """
        amount = Decimal(amount)

        # Step 1: Debit TaskWallet
        task_wallet = TaskWalletService.debit_wallet(
            user=user,
            amount=amount,
            category="transfer_to_main",
            description="Transfer to Main Wallet",
        )

        # Step 2: Credit Main Wallet
        main_wallet = WalletService.credit_wallet(
            user=user,
            amount=amount,
            category="task_wallet_transfer",
            description="Received from Task Wallet",
        )

        # Optionally: log a cross-reference transaction
        TaskWalletTransaction.objects.create(
            user=user,
            transaction_type="transfer",
            category="transfer_to_main",
            amount=amount,
            balance_before=task_wallet.balance + amount,
            balance_after=task_wallet.balance,
            description="Transferred to Main Wallet",
            reference=f"TW2MW-{timezone.now().strftime('%Y%m%d%H%M%S')}",
        )

        return {
            "success": True,
            "message": f"₦{amount} successfully moved to Main Wallet.",
            "task_wallet_balance": task_wallet.balance,
            "main_wallet_balance": getattr(main_wallet, "balance", None),
        }


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


    # tasks/services.py → TaskWalletService.release_task_escrow()

    @staticmethod
    @transaction.atomic
    def release_task_escrow(escrow, member, submission=None):
        """
        Release escrow for ONE submission only.
        CRITICAL: Assumes escrow is already locked via select_for_update() in calling code.
        """
        from wallets.services import WalletService
        
        # ✅ Re-fetch with lock if not already locked (defensive programming)
        if not hasattr(escrow, '_state') or not getattr(escrow._state, 'locked_for_update', False):
            escrow = EscrowTransaction.objects.select_for_update().get(id=escrow.id)
        
        # ✅ CRITICAL: Check status (prevents race condition)
        if escrow.status != "locked":
            logger.warning(
                f"Escrow {escrow.id} status is {escrow.status}, not 'locked'. "
                f"Already processed by another worker."
            )
            raise ValueError(f"Escrow already {escrow.status}. Cannot release.")
        
        # ✅ Check if submission already has escrow release
        if submission:
            # Check via escrow table (more reliable than hasattr)
            existing_release = EscrowTransaction.objects.filter(
                submission=submission,
                status='released'
            ).exists()
            
            if existing_release:
                logger.warning(
                    f"Submission {submission.id} already has an escrow release. "
                    f"Race condition prevented."
                )
                raise ValueError("This submission already has an escrow release")
        
        # ✅ Calculate payment (80% to member, 20% to company)
        # member_amount, company_cut = TaskWalletService.split_payment(escrow.amount_usd)
        per_slot_amount = escrow.task.payout_per_slot
        member_amount, company_cut = TaskWalletService.split_payment(per_slot_amount)
        
        # ✅ Create GLOBALLY unique reference (includes escrow ID + submission ID)
        release_ref = f"ESCROW_RELEASE_{escrow.id}_{submission.id if submission else 'MANUAL'}_{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
        
        # ✅ Double-check for duplicate credit (database-level check)
        from payments.models import PaymentTransaction as Transaction
        existing_credit = Transaction.objects.filter(
            user=member,
            category="task_payment",
            reference__startswith=f"ESCROW_RELEASE_{escrow.id}_"
        ).exists()
        
        if existing_credit:
            logger.error(
                f"Duplicate credit detected for escrow {escrow.id}. "
                f"Race condition prevented at database level."
            )
            raise ValueError("This escrow has already been credited")
        
        # ✅ Credit member's MAIN WALLET
        try:
            WalletService.credit_wallet(
                user=member,
                amount=member_amount,
                category="task_payment",
                description=f"Task: {escrow.task.title} (80% of ₦{escrow.task.payout_per_slot})",
                reference=release_ref,
                extra_data={
                    "task_id": escrow.task.id,
                    "task_title": escrow.task.title,
                    "task_payout": str(escrow.task.payout_per_slot),
                    "submission_id": submission.id if submission else None,
                    "escrow_id": escrow.id,
                    "member_share": str(member_amount),
                    "company_cut": str(company_cut),
                }
            )
            logger.info(
                f"Escrow {escrow.id}: Credited ₦{member_amount} to {member.username} "
                f"(Task: {escrow.task.title}, Payout: ₦{escrow.task.payout_per_slot})"
            )
        except Exception as e:
            logger.error(f"Failed to credit member wallet for escrow {escrow.id}: {e}")
            raise
        
        # ✅ Credit company cut
        try:
            WalletService.credit_wallet(
                user=get_company_user(),
                amount=company_cut,
                category="company_cut",
                description=f"Platform fee: {escrow.task.title}",
                reference=f"COMPANY_CUT_{escrow.id}_{submission.id if submission else 'MANUAL'}",
                extra_data={
                    "task_id": escrow.task.id,
                    "escrow_id": escrow.id,
                }
            )
        except Exception as e:
            logger.error(f"Failed to credit company wallet for escrow {escrow.id}: {e}")
            # Don't rollback - member already paid
        
        # ✅ CRITICAL: Update escrow status ATOMICALLY
        # This prevents other workers from processing the same escrow
        updated_count = EscrowTransaction.objects.filter(
            id=escrow.id,
            status='locked'  # Only update if still locked
        ).update(
            status='released',
            released_at=timezone.now(),
            submission=submission
        )
        
        if updated_count == 0:
            logger.error(
                f"Failed to update escrow {escrow.id} status. "
                f"Already processed by another worker."
            )
            raise ValueError("Escrow was already released by another process")
        
        # Refresh from DB to get updated values
        escrow.refresh_from_db()
        
        # Update linked TaskWalletTransaction if exists
        if hasattr(escrow, "taskwallet_transaction") and escrow.taskwallet_transaction:
            escrow.taskwallet_transaction.status = "success"
            escrow.taskwallet_transaction.save(update_fields=['status'])
        
        logger.info(
            f"✓ Escrow {escrow.id} released successfully: "
            f"Member={member.username} got ₦{member_amount}, "
            f"Company got ₦{company_cut}"
        )
        
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
        wallet.balance += escrow.amount_usd
        wallet.save(update_fields=['balance'])

        TaskWalletTransaction.objects.create(
            user=escrow.advertiser,
            transaction_type="credit",
            category="task_posting",
            amount=escrow.amount_usd,
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
