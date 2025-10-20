# tasks/management/commands/cleanup_duplicate_escrows.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from wallets.models import EscrowTransaction
from tasks.models import TaskWalletTransaction
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleanup duplicate escrow transactions and fix wallet balances'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Find tasks with duplicate locked escrows
        duplicate_escrows = (
            EscrowTransaction.objects
            .values('task_id')
            .annotate(count=Count('id'))
            .filter(count__gt=1, status='locked')
        )
        
        total_refunded = Decimal('0')
        tasks_fixed = 0
        
        for dup in duplicate_escrows:
            task_id = dup['task_id']
            escrows = EscrowTransaction.objects.filter(
                task_id=task_id,
                status='locked'
            ).order_by('created_at')
            
            # Keep the first, refund the rest
            first_escrow = escrows.first()
            duplicate_list = escrows.exclude(id=first_escrow.id)
            
            self.stdout.write(
                f'\nTask {task_id}: Found {duplicate_list.count()} duplicate escrows'
            )
            
            for escrow in duplicate_list:
                advertiser = escrow.advertiser
                amount = escrow.amount_usd
                
                if not dry_run:
                    with transaction.atomic():
                        # Refund to TaskWallet
                        from tasks.services import TaskWalletService
                        wallet = TaskWalletService.get_or_create_wallet(advertiser)
                        
                        before = wallet.balance
                        wallet.balance += amount
                        wallet.save(update_fields=['balance'])
                        
                        # Log refund transaction
                        TaskWalletTransaction.objects.create(
                            user=advertiser,
                            transaction_type="credit",
                            category="duplicate_escrow_refund",
                            amount=amount,
                            balance_before=before,
                            balance_after=wallet.balance,
                            description=f"Refund for duplicate escrow on task {task_id}",
                        )
                        
                        # Mark escrow as refunded
                        escrow.status = "refunded"
                        escrow.save(update_fields=['status'])
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  ✓ Refunded ₦{amount} to {advertiser.username}'
                            )
                        )
                else:
                    self.stdout.write(
                        f'  [DRY RUN] Would refund ₦{amount} to {advertiser.username}'
                    )
                
                total_refunded += amount
                tasks_fixed += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n{"[DRY RUN] Would have fixed" if dry_run else "Fixed"} '
                f'{tasks_fixed} duplicate escrows, '
                f'{"would refund" if dry_run else "refunded"} ₦{total_refunded} total'
            )
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('\nRun without --dry-run to apply changes')
            )