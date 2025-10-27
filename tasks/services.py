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
        member_amount = (amount * Decimal('0.80')).quantize(Decimal('0.01'))
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
        Release escrow for ONE submission only.
        Prevents duplicate releases via multiple safeguards:
        - Row-level locking
        - Status checks
        - Unique reference checks
        - Database constraints
        
        Args:
            escrow_or_task: Can be either an EscrowTransaction object or a Task object
            member: User receiving the payment
            submission: TaskSubmission object (optional)
        """
        member_id = member.id
        submission_id = submission.id if submission else None
        
        # ✅ Handle both escrow object and task object
        if isinstance(escrow_or_task, EscrowTransaction):
            escrow_id = escrow_or_task.id
            task_id = escrow_or_task.task.id if hasattr(escrow_or_task, 'task') else None
        else:
            # Assume it's a Task object, fetch the escrow
            task_id = escrow_or_task.id
            logger.info(
                f"[ESCROW_RELEASE] Fetching escrow for task - "
                f"Task: {task_id}, Submission: {submission_id}"
            )
            try:
                escrow_lookup = EscrowTransaction.objects.get(
                    task_id=task_id,
                    status="locked"
                )
                escrow_id = escrow_lookup.id
                logger.info(
                    f"[ESCROW_RELEASE] Found escrow - "
                    f"Escrow: {escrow_id} for Task: {task_id}"
                )
            except EscrowTransaction.DoesNotExist:
                logger.error(
                    f"[ESCROW_RELEASE] FAILED - No locked escrow found for task {task_id}"
                )
                raise ValueError(
                    f"No locked escrow found for task {task_id}. "
                    f"Either escrow doesn't exist or already released."
                )
            except EscrowTransaction.MultipleObjectsReturned:
                logger.error(
                    f"[ESCROW_RELEASE] FAILED - Multiple locked escrows for task {task_id}"
                )
                raise ValueError(
                    f"Multiple locked escrows found for task {task_id}. "
                    f"Please contact support."
                )
        
        logger.info(
            f"[ESCROW_RELEASE] Starting release - "
            f"Escrow: {escrow_id}, Task: {task_id}, Member: {member_id}, Submission: {submission_id}"
        )
        
        # ✅ Lock the escrow row for update (CRITICAL for race condition prevention)
        try:
            escrow = (
                EscrowTransaction.objects
                .select_for_update(nowait=False)  # Wait for lock
                .get(id=escrow_id)
            )
            logger.info(
                f"[ESCROW_RELEASE] Escrow locked - "
                f"ID: {escrow_id}, Status: {escrow.status}, Amount: {escrow.amount_usd}"
            )
        except EscrowTransaction.DoesNotExist:
            logger.error(f"[ESCROW_RELEASE] FAILED - Escrow {escrow_id} not found")
            raise ValueError(f"Escrow {escrow_id} does not exist")

        # ✅ INFO-ONLY CHECK: Log slot status but don't block release
        task = escrow.task
        filled_slots = Submission.objects.filter(task=task, status="approved").count()
        total_slots = getattr(task, "slots", None) or getattr(task, "total_slots", None)

        if total_slots is None:
            logger.warning(
                f"[ESCROW_RELEASE] Task {task.id} has no 'slots' or 'total_slots' defined."
            )
        else:
            logger.info(
                f"[ESCROW_RELEASE] Slot check - Approved: {filled_slots}/{total_slots}"
            )
            if filled_slots < total_slots:
                logger.info(
                    f"[ESCROW_RELEASE] Partial release allowed - "
                    f"Escrow stays locked until all slots filled. "
                    f"Approved: {filled_slots}/{total_slots}, Task: {task.id}"
                )

        # ✅ FIRST CHECK: Escrow status
        if escrow.status != "locked":
            logger.warning(
                f"[ESCROW_RELEASE] BLOCKED - Invalid status - "
                f"Escrow: {escrow_id}, Status: {escrow.status}, Expected: locked"
            )
            raise ValueError(
                f"Escrow already {escrow.status}. Cannot release. "
                f"Escrow ID: {escrow_id}"
            )
        
        # ✅ SECOND CHECK: Submission already linked to escrow
        if submission and hasattr(submission, 'escrow_release') and submission.escrow_release:
            logger.warning(
                f"[ESCROW_RELEASE] BLOCKED - Duplicate release - "
                f"Submission: {submission_id} already linked to escrow: {submission.escrow_release.id}"
            )
            raise ValueError(
                f"This submission already has an escrow release: {submission.escrow_release.id}"
            )
        
       
        # ✅ Calculate payment split
        member_amount, company_cut = TaskWalletService.split_payment(escrow.task.payout_per_slot)
        
        logger.info(
            f"[ESCROW_RELEASE] Payment split - "
            f"Total: {escrow.task.payout_per_slot}, Member: {member_amount}, Company: {company_cut}"
        )
        
        # ✅ Create unique reference
        release_ref = f"ESCROW_RELEASE_{escrow_id}_{submission_id or 'MANUAL'}_{timezone.now().timestamp()}"
        
        # ✅ FOURTH CHECK: Duplicate credit prevention
        from payments.models import PaymentTransaction as Transaction
        existing_credit = Transaction.objects.filter(
            reference__startswith=f"ESCROW_RELEASE_{escrow_id}_{submission_id or 'MANUAL'}"
        ).exists()
        
        if existing_credit:
            logger.error(
                f"[ESCROW_RELEASE] BLOCKED - Duplicate credit detected - "
                f"Reference pattern: ESCROW_RELEASE_{escrow_id}_{submission_id}"
            )
            raise ValueError(
                f"This escrow has already been credited. Escrow ID: {escrow_id}"
            )
        
        from wallets.services import WalletService
        
        # ✅ Credit member's MAIN WALLET
        try:
            logger.info(
                f"[ESCROW_RELEASE] Crediting member wallet - "
                f"Member: {member_id}, Amount: {member_amount}"
            )
            
            TaskWalletService.credit_wallet(
                user=member,
                amount=member_amount,
                category="task_payment",
                description=f"Task: {escrow.task.title})",
                reference=release_ref,
            )
            
            logger.info(
                f"[ESCROW_RELEASE] Member credited successfully - "
                f"Member: {member_id}, Amount: {member_amount}"
            )
            
        except Exception as e:
            logger.error(
                f"[ESCROW_RELEASE] FAILED to credit member - "
                f"Member: {member_id}, Error: {str(e)}, Escrow: {escrow_id}"
            )
            raise ValueError(f"Failed to credit member wallet: {str(e)}")
        
        # ✅ Credit company cut
        try:
            company_ref = f"COMPANY_CUT_{escrow_id}_{submission_id or 'MANUAL'}_{timezone.now().timestamp()}"
            
            logger.info(
                f"[ESCROW_RELEASE] Crediting company wallet - Amount: {company_cut}"
            )
            
            WalletService.credit_wallet(
                user=get_company_user(),
                amount=company_cut,
                category="company_cut",
                description=f"Platform fee: {escrow.task.title}",
                reference=company_ref,
                extra_data={
                    "task_id": escrow.task.id,
                    "escrow_id": escrow_id,
                    "submission_id": submission_id,
                    "member_payment": str(member_amount),
                }
            )
            
            logger.info(
                f"[ESCROW_RELEASE] Company credited successfully - Amount: {company_cut}"
            )
            
        except Exception as e:
            logger.error(
                f"[ESCROW_RELEASE] WARNING - Failed to credit company wallet - "
                f"Error: {str(e)}, Escrow: {escrow_id}"
            )
            logger.critical(
                f"[ESCROW_RELEASE] MANUAL_ACTION_REQUIRED - "
                f"Member paid but company cut failed - "
                f"Escrow: {escrow_id}, Company amount: {company_cut}"
            )
        
        # ✅ Update escrow status conditionally (only mark as released when all slots are filled)
        try:
            task = escrow.task
            filled_slots = Submission.objects.filter(task=task, status="approved").count()
            total_slots = getattr(task, "slots", None) or getattr(task, "total_slots", None)

            if total_slots and filled_slots >= total_slots:
                escrow.status = "released"
                escrow.released_at = timezone.now()
                logger.info(
                    f"[ESCROW_RELEASE] All slots filled - Escrow released. "
                    f"Approved: {filled_slots}/{total_slots}, Task: {task.id}"
                )
            else:
                logger.info(
                    f"[ESCROW_RELEASE] Partial release - Escrow stays locked. "
                    f"Approved: {filled_slots}/{total_slots}, Task: {task.id}"
                )

            if submission:
                escrow.submission = submission

            escrow.save(update_fields=['status', 'released_at', 'submission'])

        except Exception as e:
            logger.error(
                f"[ESCROW_RELEASE] FAILED to update escrow status - "
                f"Escrow: {escrow_id}, Error: {str(e)}"
            )
            raise
        
        # ✅ Update linked transaction if exists
        if hasattr(escrow, "taskwallet_transaction") and escrow.taskwallet_transaction:
            try:
                escrow.taskwallet_transaction.status = "released"
                escrow.taskwallet_transaction.save(update_fields=['status'])
                
                logger.info(
                    f"[ESCROW_RELEASE] Transaction updated - "
                    f"ID: {escrow.taskwallet_transaction.id}"
                )
            except Exception as e:
                logger.warning(
                    f"[ESCROW_RELEASE] Failed to update transaction status - "
                    f"Transaction: {escrow.taskwallet_transaction.id}, Error: {str(e)}"
                )
        
        logger.info(
            f"[ESCROW_RELEASE] SUCCESS - "
            f"Escrow: {escrow_id}, Member: {member.username} (₦{member_amount}), "
            f"Company: ₦{company_cut}, Submission: {submission_id}"
        )
        
        return escrow




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
            f"[ESCROW_REFUND] Escrow status updated to refunded"  # noqa: F541
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



