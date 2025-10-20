# tasks/management/commands/visualize_payment_problem.py

from django.core.management.base import BaseCommand
from tasks.models import Submission, Task, TaskWalletTransaction
from wallets.models import EscrowTransaction
from payments.models import PaymentTransaction as Transaction
from decimal import Decimal

class Command(BaseCommand):
    help = 'Visualize the exact payment problem with real data'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('\n' + '=' * 100))
        self.stdout.write(self.style.WARNING('VISUAL PAYMENT PROBLEM ANALYSIS'))
        self.stdout.write(self.style.WARNING('=' * 100 + '\n'))
        
        # Pick a specific problematic user from the data
        # Oluwanisola Joel received ₦58,000 + ₦13,920 + multiple ₦6,960 payments
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            user = User.objects.get(username='Oluwanisola Joel')
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('User not found. Using first user with submissions...'))
            user = Submission.objects.filter(status='approved').first().member
        
        self.stdout.write(f'👤 Analyzing user: {user.username}\n')
        
        # Get all approved submissions
        submissions = Submission.objects.filter(
            member=user,
            status='approved'
        ).select_related('task').order_by('reviewed_at')
        
        self.stdout.write(f'📝 Approved submissions: {submissions.count()}\n')
        
        # Expected total
        expected_total = Decimal('0')
        
        self.stdout.write('━' * 100)
        self.stdout.write('EXPECTED PAYMENTS (Based on Approved Submissions):')
        self.stdout.write('━' * 100 + '\n')
        
        for i, submission in enumerate(submissions, 1):
            task_payout = submission.task.payout_per_slot
            member_share = task_payout * Decimal('0.80')  # 80% after platform fee
            expected_total += member_share
            
            self.stdout.write(
                f'{i:2d}. Task #{submission.task.id}: {submission.task.title[:50]}'
            )
            self.stdout.write(
                f'    Task Payout: ₦{task_payout}  →  Member Should Get: ₦{member_share} (80%)'
            )
            self.stdout.write(
                f'    Approved: {submission.reviewed_at.strftime("%Y-%m-%d %H:%M") if submission.reviewed_at else "N/A"}'
            )
            self.stdout.write('')
        
        self.stdout.write(f'💰 EXPECTED TOTAL: ₦{expected_total}\n')
        
        # Actual credits received
        self.stdout.write('━' * 100)
        self.stdout.write('ACTUAL CREDITS RECEIVED:')
        self.stdout.write('━' * 100 + '\n')
        
        # TaskWallet credits
        tw_credits = TaskWalletTransaction.objects.filter(
            user=user,
            transaction_type='credit'
        ).exclude(
            category__in=['topup_from_main', 'admin_adjustment', 'subscription_bonus']
        ).order_by('created_at')
        
        tw_total = Decimal('0')
        
        if tw_credits.exists():
            self.stdout.write('📱 TaskWallet Credits:')
            for credit in tw_credits:
                tw_total += credit.amount
                self.stdout.write(
                    f'   ₦{credit.amount:>10}  |  {credit.created_at.strftime("%Y-%m-%d %H:%M")}  |  '
                    f'{credit.description or "No description"}'
                )
            self.stdout.write(f'\n   TaskWallet Total: ₦{tw_total}\n')
        
        # Main Wallet credits
        main_credits = Transaction.objects.filter(
            user=user,
            transaction_type='credit',
            category='task_payment'
        ).order_by('created_at')
        
        main_total = Decimal('0')
        
        if main_credits.exists():
            self.stdout.write('💳 Main Wallet Credits:')
            for credit in main_credits:
                main_total += credit.amount
                self.stdout.write(
                    f'   ₦{credit.amount:>10}  |  {credit.created_at.strftime("%Y-%m-%d %H:%M")}  |  '
                    f'{credit.description or "No description"}'
                )
            self.stdout.write(f'\n   Main Wallet Total: ₦{main_total}\n')
        
        actual_total = tw_total + main_total
        
        self.stdout.write(f'💰 ACTUAL TOTAL RECEIVED: ₦{actual_total}\n')
        
        # Compare
        self.stdout.write('━' * 100)
        self.stdout.write('DISCREPANCY ANALYSIS:')
        self.stdout.write('━' * 100 + '\n')
        
        difference = actual_total - expected_total
        
        self.stdout.write(f'Expected:  ₦{expected_total:>12}')
        self.stdout.write(f'Actual:    ₦{actual_total:>12}')
        self.stdout.write(f'Difference: ₦{difference:>11}')
        
        if difference > Decimal('0.01'):
            multiplier = actual_total / expected_total if expected_total > 0 else 0
            self.stdout.write(
                self.style.ERROR(
                    f'\n❌ OVERPAID by ₦{difference} ({multiplier:.1f}x the expected amount)'
                )
            )
        elif difference < Decimal('-0.01'):
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  UNDERPAID by ₦{abs(difference)}'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    '\n✓ Payment amount is CORRECT'
                )
            )
        
        # Check for duplicate escrow releases
        self.stdout.write('\n' + '━' * 100)
        self.stdout.write('ESCROW ANALYSIS:')
        self.stdout.write('━' * 100 + '\n')
        
        tasks_with_submissions = Task.objects.filter(
            submissions__member=user,
            submissions__status='approved'
        ).distinct()
        
        for task in tasks_with_submissions:
            escrows = EscrowTransaction.objects.filter(task=task)
            escrow_count = escrows.count()
            
            if escrow_count > 1:
                self.stdout.write(
                    self.style.ERROR(
                        f'❌ Task #{task.id}: {escrow_count} escrows found (SHOULD BE 1)'
                    )
                )
                for escrow in escrows:
                    self.stdout.write(
                        f'   • Escrow #{escrow.id}: ₦{escrow.amount_usd} - Status: {escrow.status} - '
                        f'Created: {escrow.created_at.strftime("%Y-%m-%d %H:%M")}'
                    )
            elif escrow_count == 1:
                escrow = escrows.first()
                icon = '✅' if escrow.status == 'released' else '🔒'
                self.stdout.write(
                    f'{icon} Task #{task.id}: 1 escrow (Status: {escrow.status})'
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️  Task #{task.id}: NO escrow found'
                    )
                )
        
        # Root cause summary
        self.stdout.write('\n' + '━' * 100)
        self.stdout.write(self.style.ERROR('🔍 ROOT CAUSE SUMMARY:'))
        self.stdout.write('━' * 100 + '\n')
        
        if difference > expected_total * Decimal('0.5'):  # More than 50% overpaid
            self.stdout.write(
                '1. Multiple escrow releases happening per submission'
            )
            self.stdout.write(
                '2. Likely caused by BOTH signal handlers AND manual release in views'
            )
            self.stdout.write(
                '3. Possibly multiple duplicate escrows per task'
            )
        
        self.stdout.write('\n' + '━' * 100)
        self.stdout.write(self.style.WARNING('RECOMMENDED ACTIONS:'))
        self.stdout.write('━' * 100 + '\n')
        
        self.stdout.write('1. Run: python manage.py debug_escrow_releases')
        self.stdout.write('2. Remove signal handlers from tasks/signals.py')
        self.stdout.write('3. Add database constraints for unique locked escrow per task')
        self.stdout.write('4. Update release_task_escrow() with duplicate prevention')
        self.stdout.write('5. Run: python manage.py cleanup_duplicate_escrows')
        self.stdout.write('6. Run: python manage.py recalculate_and_fix_overpayments --fix-overpayments')
        
        self.stdout.write('\n')