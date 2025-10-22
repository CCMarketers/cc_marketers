# tasks/services/task_wallet_service.py
from decimal import Decimal
import logging
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model

from wallets.models import EscrowTransaction
from .models import Submission, TaskWallet, TaskWalletTransaction
from django.db.models import F
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
    # @staticmethod
    # def split_payment(amount, company_rate=Decimal("0.10")):
    #     """
    #     Split escrow amount between worker and company.
    #     Returns (member_amount, company_cut)
    #     """
    #     amount = Decimal(amount)
    #     company_cut = (amount * company_rate).quantize(Decimal("0.01"))
    #     member_amount = amount - company_cut
    #     return member_amount, company_cut

    @staticmethod
    def split_payment(amount):
        """
        Split payment: 90% to member, 10% to company.
        """
        amount = Decimal(amount)
        member_amount = (amount * Decimal('0.90')).quantize(Decimal('0.01'))
        company_cut = amount - member_amount  # Ensures exact total
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
        Prevents race conditions using select_for_update and optimistic locking.
        """
        amount = Decimal(amount)
        
        logger.info(
            f"[ESCROW_CREATE] Starting escrow creation - "
            f"User: {advertiser.id}, Task: {task.id}, Amount: {amount}"
        )
        
        # ✅ Lock wallet row to prevent concurrent modifications
        wallet = (
            TaskWallet.objects
            .select_for_update(nowait=False)  # Wait for lock instead of failing
            .get(user=advertiser)
        )
        
        logger.info(
            f"[ESCROW_CREATE] Wallet locked - "
            f"Current balance: {wallet.balance}, Required: {amount}"
        )
        
        # ✅ Check sufficient balance
        if wallet.balance < amount:
            logger.error(
                f"[ESCROW_CREATE] FAILED - Insufficient balance - "
                f"User: {advertiser.id}, Balance: {wallet.balance}, Required: {amount}"
            )
            raise ValueError(
                f"Insufficient Task Wallet balance. Available: {wallet.balance}, Required: {amount}"
            )
        
        # ✅ Check for duplicate escrow (prevent double-charging)
        existing_escrow = EscrowTransaction.objects.filter(
            task=task,
            advertiser=advertiser,
            status__in=["locked", "released"]
        ).exists()
        
        if existing_escrow:
            logger.error(
                f"[ESCROW_CREATE] FAILED - Duplicate escrow detected - "
                f"Task: {task.id}, Advertiser: {advertiser.id}"
            )
            raise ValueError("Escrow already exists for this task")
        
        # ✅ Deduct balance atomically
        before_balance = wallet.balance
        wallet.balance = F('balance') - amount
        wallet.save(update_fields=['balance'])
        wallet.refresh_from_db()  # Get actual balance after atomic update
        
        logger.info(
            f"[ESCROW_CREATE] Balance deducted - "
            f"Before: {before_balance}, After: {wallet.balance}"
        )
        
        # ✅ Create transaction record
        txn = TaskWalletTransaction.objects.create(
            user=advertiser,
            transaction_type="debit",
            category="task_posting",
            amount=amount,
            balance_before=before_balance,
            balance_after=wallet.balance,
            description=f"Escrow for task: {task.title}",
            status="pending",
        )
        
        logger.info(f"[ESCROW_CREATE] Transaction created - ID: {txn.id}")
        
        # ✅ Create escrow with unique constraint protection
        try:
            escrow = EscrowTransaction.objects.create(
                task=task,
                advertiser=advertiser,
                amount_usd=amount,
                taskwallet_transaction=txn,
                status="locked",
            )
            
            # Mark transaction as success
            txn.status = "success"
            txn.save(update_fields=['status'])
            
            logger.info(
                f"[ESCROW_CREATE] SUCCESS - Escrow created - "
                f"ID: {escrow.id}, Task: {task.id}, Amount: {amount}"
            )
            
            return escrow
            
        except Exception as e:
            logger.error(
                f"[ESCROW_CREATE] FAILED during escrow creation - "
                f"Error: {str(e)}, Task: {task.id}"
            )
            # Transaction will rollback automatically
            raise

    @staticmethod
    @transaction.atomic
    def release_task_escrow(escrow_or_task, member, submission=None):
        """
        Safe multi-payout escrow release.
        - Each approved submission triggers a separate partial release.
        - Escrow only fully releases when all slots are approved.
        - No new model or schema changes required.
        - Race-condition proof with select_for_update.
        """
        from payments.models import PaymentTransaction as Transaction

        member_id = member.id
        submission_id = submission.id if submission else None

        # Resolve escrow
        if isinstance(escrow_or_task, EscrowTransaction):
            escrow = escrow_or_task
        else:
            escrow = EscrowTransaction.objects.filter(task=escrow_or_task, status="locked").first()
            if not escrow:
                raise ValueError(f"No locked escrow found for task {escrow_or_task.id}")

        # Lock the escrow row for update (ensures race safety)
        escrow = EscrowTransaction.objects.select_for_update().get(id=escrow.id)

        # Safety check
        if escrow.status != "locked":
            raise ValueError(f"Escrow already {escrow.status}, cannot release again")

        task = escrow.task

        # ✅ Prevent duplicate release for the same submission
        if submission:
            duplicate_ref_prefix = f"ESCROW_RELEASE_{escrow.id}_{submission.id}"
            if Transaction.objects.filter(reference__startswith=duplicate_ref_prefix).exists():
                return f"Skipped: Submission {submission.id} already paid"

        # ✅ Check slot fill status
        filled_slots = Submission.objects.filter(task=task, status="approved").count()
        total_slots = getattr(task, "slots", None) or getattr(task, "total_slots", None)

        if total_slots is None:
            raise ValueError(f"Task {task.id} missing slot count field")

        # ✅ If not all slots are filled, release only this submission’s payout
        if filled_slots < total_slots:
            release_type = "partial"
        else:
            release_type = "full"

        # ✅ Split payment
        member_amount, company_cut = TaskWalletService.split_payment(task.payout_per_slot)

        # ✅ Credit member
        release_ref = f"ESCROW_RELEASE_{escrow.id}_{submission_id}_{timezone.now().timestamp()}"
        TaskWalletService.credit_wallet(
            user=member,
            amount=member_amount,
            category="task_payment",
            description=f"Task: {task.title}",
            reference=release_ref,
        )

        # ✅ Credit company
        company_ref = f"COMPANY_CUT_{escrow.id}_{submission_id}_{timezone.now().timestamp()}"
        WalletService.credit_wallet(
            user=get_company_user(),
            amount=company_cut,
            category="company_cut",
            description=f"Platform fee: {task.title}",
            reference=company_ref,
        )

        # ✅ Update escrow only when fully filled
        if release_type == "full":
            escrow.status = "released"
            escrow.released_at = timezone.now()
            escrow.save(update_fields=["status", "released_at"])
        else:
            # leave it locked until all slots filled
            escrow.save(update_fields=["updated_at"])  # just to trigger row write

        return f"Escrow {escrow.id} {release_type} release successful for submission {submission_id}"


    @staticmethod
    def get_task_escrow(task):
        """
        Get the locked escrow for a task.
        Useful helper to avoid passing wrong IDs.
        
        Args:
            task: Task object or task ID
            
        Returns:
            EscrowTransaction object
            
        Raises:
            ValueError: If no locked escrow found or multiple found
        """
        from tasks.models import Task
        
        task_id = task.id if isinstance(task, Task) else task
        
        logger.info(f"[GET_ESCROW] Looking for locked escrow - Task: {task_id}")
        
        try:
            escrow = EscrowTransaction.objects.get(
                task_id=task_id,
                status="locked"
            )
            logger.info(
                f"[GET_ESCROW] Found escrow - "
                f"Escrow: {escrow.id}, Amount: {escrow.amount_usd}"
            )
            return escrow
            
        except EscrowTransaction.DoesNotExist:
            logger.error(
                f"[GET_ESCROW] FAILED - No locked escrow for task {task_id}"
            )
            raise ValueError(
                f"No locked escrow found for task {task_id}. "
                f"Task may not have escrow or already released."
            )
            
        except EscrowTransaction.MultipleObjectsReturned:
            logger.error(
                f"[GET_ESCROW] FAILED - Multiple locked escrows for task {task_id}"
            )
            raise ValueError(
                f"Data integrity issue: Multiple locked escrows for task {task_id}"
            )


    @staticmethod
    @transaction.atomic
    def refund_task_escrow(escrow):
        """
        Refund locked escrow back to advertiser's task wallet.
        Used when task is deleted or dispute resolved in favor of advertiser.
        Race-condition safe with proper locking.
        
        Args:
            escrow: EscrowTransaction object
            
        Returns:
            Updated EscrowTransaction object
            
        Raises:
            ValueError: If escrow is not in 'locked' status
        """
        escrow_id = escrow.id
        
        logger.info(
            f"[ESCROW_REFUND] Starting refund - Escrow: {escrow_id}"
        )
        
        # ✅ Lock the escrow row to prevent concurrent refunds
        try:
            escrow = (
                EscrowTransaction.objects
                .select_for_update(nowait=False)
                .get(id=escrow_id)
            )
            logger.info(
                f"[ESCROW_REFUND] Escrow locked - "
                f"Status: {escrow.status}, Amount: {escrow.amount_usd}"
            )
        except EscrowTransaction.DoesNotExist:
            logger.error(f"[ESCROW_REFUND] FAILED - Escrow {escrow_id} not found")
            raise ValueError(f"Escrow {escrow_id} does not exist")
        
        # ✅ Verify status (race condition check)
        if escrow.status != "locked":
            logger.warning(
                f"[ESCROW_REFUND] BLOCKED - Invalid status - "
                f"Escrow: {escrow_id}, Status: {escrow.status}, Expected: locked"
            )
            raise ValueError(
                f"Escrow already {escrow.status}. Cannot refund. Escrow ID: {escrow_id}"
            )
        
        # ✅ Get and lock advertiser's wallet
        wallet = TaskWalletService.get_or_create_wallet(escrow.advertiser)
        # Re-lock wallet in this transaction
        wallet = TaskWallet.objects.select_for_update(nowait=False).get(id=wallet.id)
        
        logger.info(
            f"[ESCROW_REFUND] Wallet locked - "
            f"User: {escrow.advertiser.id}, Current balance: {wallet.balance}"
        )
        
        # ✅ Credit back to advertiser's task wallet atomically
        balance_before = wallet.balance
        wallet.balance = F('balance') + escrow.amount_usd
        wallet.save(update_fields=['balance'])
        wallet.refresh_from_db()
        
        logger.info(
            f"[ESCROW_REFUND] Balance credited - "
            f"Before: {balance_before}, After: {wallet.balance}, Added: {escrow.amount_usd}"
        )
        
        # ✅ Create transaction record
        try:
            txn = TaskWalletTransaction.objects.create(
                user=escrow.advertiser,
                transaction_type="credit",
                category="escrow_refund",
                amount=escrow.amount_usd,
                balance_before=balance_before,
                balance_after=wallet.balance,
                description=f"Refund for task: {escrow.task.title}",
                status="success"
            )
            logger.info(f"[ESCROW_REFUND] Transaction created - ID: {txn.id}")
        except Exception as e:
            logger.error(
                f"[ESCROW_REFUND] Failed to create transaction record: {e}"
            )
            # Don't rollback - money already credited, this is just for audit trail
        
        # ✅ Update escrow status
        escrow.status = "refunded"
        escrow.refunded_at = timezone.now()
        escrow.save(update_fields=['status', 'refunded_at'])
        
        logger.info(
            f"[ESCROW_REFUND] Escrow status updated to refunded"
        )
        
        # ✅ Update linked original transaction if exists
        if hasattr(escrow, "taskwallet_transaction") and escrow.taskwallet_transaction:
            try:
                escrow.taskwallet_transaction.status = "refunded"
                escrow.taskwallet_transaction.save(update_fields=['status'])
                logger.info(
                    f"[ESCROW_REFUND] Original transaction updated - "
                    f"ID: {escrow.taskwallet_transaction.id}"
                )
            except Exception as e:
                logger.warning(
                    f"[ESCROW_REFUND] Failed to update original transaction status: {e}"
                )
        
        logger.info(
            f"[ESCROW_REFUND] SUCCESS - "
            f"Escrow: {escrow_id}, Amount: ₦{escrow.amount_usd} refunded to {escrow.advertiser.username}"
        )
        
        return escrow