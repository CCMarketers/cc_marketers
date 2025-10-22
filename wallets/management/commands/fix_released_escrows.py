"""
Complete Script: Fix Released Escrows
File: wallets/management/commands/fix_released_escrows.py

Updates existing released escrows to locked with correct amounts
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from tasks.models import Submission, TaskWallet, TaskWalletTransaction
from wallets.models import EscrowTransaction


class Command(BaseCommand):
    help = "Fix escrow amounts and status for tasks with unfilled slots"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview changes without executing'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Attempt to fix all tasks (even with insufficient balance)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options.get('force', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("=== DRY RUN MODE ===\n"))
        
        # Find all released escrows with unfilled slots
        released_escrows = EscrowTransaction.objects.filter(
            status="released"
        ).select_related('task', 'task__advertiser')
        
        to_fix = []
        total_top_up = Decimal('0')
        
        self.stdout.write("Analyzing tasks...\n")
        
        for escrow in released_escrows:
            task = escrow.task
            
            # Count approved submissions
            approved = Submission.objects.filter(
                task=task, 
                status="approved"
            ).count()
            
            # Calculate unfilled slots
            unfilled = task.total_slots - approved
            
            if unfilled > 0:
                # What escrow SHOULD have for remaining slots
                should_have = task.payout_per_slot * unfilled
                
                # What it currently has
                current_amount = escrow.amount_usd
                
                # How much to add
                top_up = should_have - current_amount
                
                # Check wallet balance
                try:
                    wallet = TaskWallet.objects.get(user=task.advertiser)
                    wallet_balance = wallet.balance
                except TaskWallet.DoesNotExist:
                    wallet_balance = Decimal('0')
                
                can_afford = wallet_balance >= top_up if top_up > 0 else True
                
                to_fix.append({
                    'escrow': escrow,
                    'task': task,
                    'unfilled': unfilled,
                    'current_amount': current_amount,
                    'should_have': should_have,
                    'top_up': top_up,
                    'wallet_balance': wallet_balance,
                    'can_afford': can_afford,
                })
                
                if top_up > 0:
                    total_top_up += top_up
                
                status = "OK" if can_afford or top_up <= 0 else "INSUFFICIENT"
                
                self.stdout.write(
                    f"\n{'-' * 80}\n"
                    f"Task {task.id}: {task.title}\n"
                    f"  Advertiser: {task.advertiser.username}\n"
                    f"  Unfilled slots: {unfilled} x N{task.payout_per_slot} = N{should_have}\n"
                    f"  Current escrow: N{current_amount}\n"
                    f"  Top-up needed: N{top_up}\n"
                    f"  Wallet balance: N{wallet_balance}\n"
                    f"  Status: {status}\n"
                )
        
        if not to_fix:
            self.stdout.write(self.style.SUCCESS("\n✓ No tasks need fixing!"))
            return
        
        # Separate fixable and unfixable
        can_fix = [x for x in to_fix if x['can_afford'] or x['top_up'] <= 0]
        cannot_fix = [x for x in to_fix if not x['can_afford'] and x['top_up'] > 0]
        
        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write(f"\n✓ Can fix: {len(can_fix)} tasks")
        self.stdout.write(f"\n✗ Cannot fix: {len(cannot_fix)} tasks (insufficient balance)")
        self.stdout.write(f"\nTotal top-up needed: N{total_top_up}")
        self.stdout.write(f"\n{'=' * 80}\n")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n✓ Dry run complete. Use without --dry-run to execute."))
            return
        
        if not can_fix and not force:
            self.stdout.write(
                self.style.WARNING(
                    "\nNo tasks can be fixed (insufficient balance).\n"
                    "Top up advertiser wallets or use --force to attempt all."
                )
            )
            return
        
        # Confirm before proceeding
        tasks_to_process = to_fix if force else can_fix
        confirm = input(f"\nProceed with fixing {len(tasks_to_process)} tasks? (yes/no): ")
        
        if confirm.lower() != 'yes':
            self.stdout.write(self.style.WARNING("Aborted by user."))
            return
        
        # Execute fixes
        success = 0
        failed = 0
        
        for item in tasks_to_process:
            try:
                self.fix_task_escrow(item)
                success += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Task {item['task'].id}: "
                        f"Top-up N{item['top_up'] if item['top_up'] > 0 else 0}, "
                        f"Escrow now N{item['should_have']} (locked)"
                    )
                )
            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"✗ Task {item['task'].id}: {str(e)}"
                    )
                )
        
        self.stdout.write(f"\n{'=' * 80}")
        self.stdout.write(f"\n✓ Successfully fixed: {success}")
        self.stdout.write(f"\n✗ Failed: {failed}")
        self.stdout.write(f"\n{'=' * 80}\n")

    @transaction.atomic
    def fix_task_escrow(self, item):
        """
        Fix a single task by:
        1. Locking the EXISTING released escrow
        2. Topping up the amount if needed
        3. Changing status to 'locked'
        """
        task = item['task']
        top_up = item['top_up']
        
        # ✅ Lock EXISTING escrow (don't create new)
        escrow = EscrowTransaction.objects.select_for_update().get(
            id=item['escrow'].id
        )
        
        # Lock wallet
        wallet = TaskWallet.objects.select_for_update().get(
            user=task.advertiser
        )
        
        # Deduct top-up amount if needed
        if top_up > 0:
            if wallet.balance < top_up:
                raise ValueError(
                    f"Insufficient balance. Has: N{wallet.balance}, Needs: N{top_up}"
                )
            
            balance_before = wallet.balance
            wallet.balance -= top_up
            wallet.save(update_fields=['balance'])
            
            # Create transaction record
            TaskWalletTransaction.objects.create(
                user=task.advertiser,
                transaction_type="debit",
                category="escrow_correction",
                amount=top_up,
                balance_before=balance_before,
                balance_after=wallet.balance,
                description=f"Escrow top-up: {task.title} ({item['unfilled']} slots)",
                status="success"
            )
        
        # ✅ UPDATE existing escrow (don't create new)
        escrow.amount_usd = item['should_have']  # Set to correct amount
        escrow.status = "locked"
        escrow.released_at = None
        escrow.submission = None
        escrow.save(update_fields=['amount_usd', 'status', 'released_at', 'submission'])
        
        return escrow