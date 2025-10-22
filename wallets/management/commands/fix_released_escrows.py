"""
Django Management Command: Fix Released Escrows
python manage.py fix_released_escrows --dry-run  # Preview changes
python manage.py fix_released_escrows             # Execute fix
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from tasks.models import  Submission, TaskWallet, TaskWalletTransaction
from wallets.models import EscrowTransaction
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix escrows that were released early and recreate locked escrows for unfilled slots"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without executing',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE - No changes will be made ===\n"))
        
        # Find all tasks with released escrows but unfilled slots
        problematic_tasks = self.find_problematic_tasks()
        
        if not problematic_tasks:
            self.stdout.write(self.style.SUCCESS("✓ No problematic tasks found. All escrows are correct!"))
            return
        
        self.stdout.write(self.style.WARNING(f"\nFound {len(problematic_tasks)} tasks with issues:\n"))
        
        total_to_lock = Decimal('0')
        fixes = []
        
        for task_data in problematic_tasks:
            task = task_data['task']
            unfilled_slots = task_data['unfilled_slots']
            amount_needed = task_data['amount_needed']
            approved_count = task_data['approved_count']
            
            self.stdout.write(
                f"\n{'─' * 80}\n"
                f"Task ID: {task.id} - {task.title}\n"
                f"Advertiser: {task.advertiser.username} ({task.advertiser.id})\n"
                f"Total Slots: {task.total_slots} | Approved: {approved_count} | Unfilled: {unfilled_slots}\n"
                f"Payout per slot: ₦{task.payout_per_slot}\n"
                f"Amount needed for unfilled: ₦{amount_needed}\n"
                f"Released escrow: {task_data['released_escrow_id']}\n"
            )
            
            total_to_lock += amount_needed
            fixes.append(task_data)
        
        self.stdout.write(
            f"\n{'=' * 80}\n"
            f"SUMMARY:\n"
            f"Tasks to fix: {len(fixes)}\n"
            f"Total amount to lock: ₦{total_to_lock}\n"
            f"{'=' * 80}\n"
        )
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n✓ Dry run complete. Use without --dry-run to execute fixes."))
            return
        
        # Ask for confirmation
        confirm = input("\nProceed with fixing these tasks? (yes/no): ")
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.WARNING("Aborted by user."))
            return
        
        # Execute fixes
        success_count = 0
        error_count = 0
        
        for task_data in fixes:
            try:
                self.fix_task_escrow(task_data)
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f"✓ Fixed task {task_data['task'].id}"))
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f"✗ Failed task {task_data['task'].id}: {e}"))
                logger.error(f"Failed to fix task {task_data['task'].id}: {e}", exc_info=True)
        
        self.stdout.write(
            f"\n{'=' * 80}\n"
            f"RESULTS:\n"
            f"✓ Successfully fixed: {success_count}\n"
            f"✗ Failed: {error_count}\n"
            f"{'=' * 80}\n"
        )

    def find_problematic_tasks(self):
        """Find tasks with released escrows but unfilled slots"""
        problematic = []
        
        # Get all tasks with released escrows
        released_escrows = EscrowTransaction.objects.filter(
            status="released"
        ).select_related('task', 'task__advertiser')
        
        for escrow in released_escrows:
            task = escrow.task
            
            # Count approved submissions
            approved_count = Submission.objects.filter(
                task=task,
                status="approved"
            ).count()
            
            # Calculate unfilled slots
            unfilled_slots = task.total_slots - approved_count
            
            # If there are unfilled slots, this is problematic
            if unfilled_slots > 0:
                amount_needed = task.payout_per_slot * unfilled_slots
                
                problematic.append({
                    'task': task,
                    'released_escrow_id': escrow.id,
                    'unfilled_slots': unfilled_slots,
                    'approved_count': approved_count,
                    'amount_needed': amount_needed,
                })
        
        return problematic

    @transaction.atomic
    def fix_task_escrow(self, task_data):
        """
        Fix a single task by:
        1. Deducting from advertiser's task wallet
        2. Creating new locked escrow for unfilled slots
        """
        task = task_data['task']
        amount_needed = task_data['amount_needed']
        unfilled_slots = task_data['unfilled_slots']
        
        logger.info(
            f"[FIX_ESCROW] Fixing task {task.id} - "
            f"Need ₦{amount_needed} for {unfilled_slots} slots"
        )
        
        # Get or create advertiser's task wallet
        wallet, created = TaskWallet.objects.get_or_create(
            user=task.advertiser,
            defaults={'balance': Decimal('0')}
        )
        
        # Lock wallet
        wallet = TaskWallet.objects.select_for_update().get(id=wallet.id)
        
        # Check if advertiser has enough balance
        if wallet.balance < amount_needed:
            raise ValueError(
                f"Insufficient balance. Has: ₦{wallet.balance}, Needs: ₦{amount_needed}"
            )
        
        # Deduct from wallet
        balance_before = wallet.balance
        wallet.balance -= amount_needed
        wallet.save(update_fields=['balance'])
        
        logger.info(
            f"[FIX_ESCROW] Deducted ₦{amount_needed} from wallet - "
            f"Before: {balance_before}, After: {wallet.balance}"
        )
        
        # Create transaction record
        txn = TaskWalletTransaction.objects.create(
            user=task.advertiser,
            transaction_type="debit",
            category="escrow_correction",
            amount=amount_needed,
            balance_before=balance_before,
            balance_after=wallet.balance,
            description=f"Escrow correction for task: {task.title} ({unfilled_slots} unfilled slots)",
            status="success"
        )
        
        # Create new locked escrow
        new_escrow = EscrowTransaction.objects.create(
            task=task,
            advertiser=task.advertiser,
            amount_usd=amount_needed,
            taskwallet_transaction=txn,
            status="locked",
        )
        
        logger.info(
            f"[FIX_ESCROW] Created new escrow {new_escrow.id} - "
            f"Amount: ₦{amount_needed}, Slots: {unfilled_slots}"
        )
        
        return new_escrow


# Alternative: Script version (if not using management command)
def fix_released_escrows_script(dry_run=True):
    """
    Standalone script version - can be run from Django shell
    Usage:
        python manage.py shell
        >>> from tasks.scripts import fix_released_escrows_script
        >>> fix_released_escrows_script(dry_run=True)  # Preview
        >>> fix_released_escrows_script(dry_run=False) # Execute
    """
    from tasks.models import Task, Submission
    from wallets.models import EscrowTransaction, TaskWallet, TaskWalletTransaction
    from decimal import Decimal
    from django.db import transaction
    from django.utils import timezone
    
    print("=" * 80)
    print("ESCROW FIX SCRIPT")
    print("=" * 80)
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made\n")
    
    # Find problematic tasks
    released_escrows = EscrowTransaction.objects.filter(status="released")
    problematic = []
    
    for escrow in released_escrows:
        task = escrow.task
        approved_count = Submission.objects.filter(task=task, status="approved").count()
        unfilled_slots = task.total_slots - approved_count
        
        if unfilled_slots > 0:
            amount_needed = task.payout_per_slot * unfilled_slots
            problematic.append({
                'task': task,
                'escrow_id': escrow.id,
                'unfilled_slots': unfilled_slots,
                'approved_count': approved_count,
                'amount_needed': amount_needed,
            })
            
            print(f"\nTask {task.id}: {task.title}")
            print(f"  Advertiser: {task.advertiser.username}")
            print(f"  Total slots: {task.total_slots} | Approved: {approved_count} | Unfilled: {unfilled_slots}")
            print(f"  Amount needed: ₦{amount_needed}")
    
    print(f"\n{'=' * 80}")
    print(f"Found {len(problematic)} tasks needing fixes")
    print(f"{'=' * 80}\n")
    
    if not problematic:
        print("✓ No issues found!")
        return
    
    if dry_run:
        print("Run with dry_run=False to execute fixes")
        return
    
    # Execute fixes
    for item in problematic:
        task = item['task']
        amount_needed = item['amount_needed']
        
        try:
            with transaction.atomic():
                wallet = TaskWallet.objects.select_for_update().get(user=task.advertiser)
                
                if wallet.balance < amount_needed:
                    print(f"✗ Task {task.id}: Insufficient balance (has: {wallet.balance}, needs: {amount_needed})")
                    continue
                
                # Deduct and create escrow
                balance_before = wallet.balance
                wallet.balance -= amount_needed
                wallet.save()
                
                txn = TaskWalletTransaction.objects.create(
                    user=task.advertiser,
                    transaction_type="debit",
                    category="escrow_correction",
                    amount=amount_needed,
                    balance_before=balance_before,
                    balance_after=wallet.balance,
                    description=f"Escrow correction: {task.title}",
                    status="success"
                )
                
                EscrowTransaction.objects.create(
                    task=task,
                    advertiser=task.advertiser,
                    amount_usd=amount_needed,
                    taskwallet_transaction=txn,
                    status="locked",
                )
                
                print(f"✓ Fixed task {task.id} - Locked ₦{amount_needed}")
                
        except Exception as e:
            print(f"✗ Task {task.id}: {e}")
    
    print("\n✓ Done!")