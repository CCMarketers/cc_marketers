# tasks/management/commands/debug_escrow_releases.py

from django.core.management.base import BaseCommand
from django.db.models import  Sum
from wallets.models import EscrowTransaction
from tasks.models import Submission, TaskWalletTransaction
from decimal import Decimal
from payments.models import PaymentTransaction as Transaction


class Command(BaseCommand):
    help = 'Debug multiple escrow releases per submission'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('ESCROW RELEASE DEBUG REPORT'))
        self.stdout.write(self.style.WARNING('=' * 80))
        
        # 1. Check for tasks with multiple escrows
        self.stdout.write('\n🔍 Checking for tasks with multiple escrow transactions...\n')
        
        from tasks.models import Task
        
        tasks_with_multiple_escrows = []
        
        for task in Task.objects.all():
            escrows = EscrowTransaction.objects.filter(task=task)
            if escrows.count() > 1:
                tasks_with_multiple_escrows.append({
                    'task': task,
                    'escrow_count': escrows.count(),
                    'escrows': list(escrows.values('id', 'status', 'amount_usd', 'created_at'))
                })
        
        if tasks_with_multiple_escrows:
            self.stdout.write(
                self.style.ERROR(
                    f'❌ Found {len(tasks_with_multiple_escrows)} tasks with MULTIPLE escrows:\n'
                )
            )
            for item in tasks_with_multiple_escrows:
                task = item['task']
                self.stdout.write(
                    f"\n  Task #{task.id}: {task.title[:50]}"
                )
                self.stdout.write(f"    Advertiser: {task.advertiser.username}")
                self.stdout.write(f"    Payout per slot: ₦{task.payout_per_slot}")
                self.stdout.write(f"    Total slots: {task.total_slots}")
                self.stdout.write(f"    Expected escrow: ₦{task.payout_per_slot * task.total_slots}")
                self.stdout.write(f"    Actual escrows: {item['escrow_count']}")
                
                total_locked = Decimal('0')
                for escrow in item['escrows']:
                    status_icon = '🔒' if escrow['status'] == 'locked' else ('✅' if escrow['status'] == 'released' else '🔙')
                    self.stdout.write(
                        f"      {status_icon} Escrow #{escrow['id']}: "
                        f"₦{escrow['amount_usd']} ({escrow['status']}) - {escrow['created_at']}"
                    )
                    if escrow['status'] == 'locked':
                        total_locked += Decimal(escrow['amount_usd'])
                
                self.stdout.write(f"    Total locked: ₦{total_locked}")
        else:
            self.stdout.write(self.style.SUCCESS('✓ No tasks with multiple escrows'))
        
        # 2. Check for submissions that triggered multiple releases
        self.stdout.write('\n\n🔍 Checking for submissions with multiple payment releases...\n')
        
        approved_submissions = Submission.objects.filter(status='approved')
        
        problem_submissions = []
        
        for submission in approved_submissions:
            # Find all task_payment credits for this member around submission approval time
            from django.utils import timezone
            from datetime import timedelta
            
            time_window_start = submission.reviewed_at - timedelta(minutes=5) if submission.reviewed_at else submission.submitted_at
            time_window_end = submission.reviewed_at + timedelta(minutes=5) if submission.reviewed_at else timezone.now()
            
            # Check TaskWallet credits
            tw_credits = TaskWalletTransaction.objects.filter(
                user=submission.member,
                transaction_type='credit',
                created_at__range=(time_window_start, time_window_end)
            )
            
            # Check Main Wallet credits
            main_credits = Transaction.objects.filter(
                user=submission.member,
                transaction_type='credit',
                category='task_payment',
                created_at__range=(time_window_start, time_window_end)
            )
            
            total_credits = tw_credits.count() + main_credits.count()
            total_amount = (
                tw_credits.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            ) + (
                main_credits.aggregate(Sum('amount_usd'))['amount_usd__sum'] or Decimal('0')
            )
            
            expected_amount = submission.task.payout_per_slot * Decimal('0.80')  # 80% after platform cut
            
            if total_credits > 1 or total_amount > expected_amount * Decimal('1.1'):  # 10% tolerance
                problem_submissions.append({
                    'submission': submission,
                    'expected': expected_amount,
                    'actual': total_amount,
                    'credit_count': total_credits,
                    'tw_credits': list(tw_credits.values('id', 'amount', 'created_at', 'description')),
                    'main_credits': list(main_credits.values('id', 'amount_usd', 'created_at', 'description'))
                })
        
        if problem_submissions:
            self.stdout.write(
                self.style.ERROR(
                    f'\n❌ Found {len(problem_submissions)} submissions with payment issues:\n'
                )
            )
            
            for item in problem_submissions:
                submission = item['submission']
                self.stdout.write(
                    f"\n  Submission #{submission.id} - Task #{submission.task.id}: {submission.task.title[:40]}"
                )
                self.stdout.write(f"    Member: {submission.member.username}")
                self.stdout.write(f"    Task payout: ₦{submission.task.payout_per_slot}")
                self.stdout.write(f"    Expected credit (80%): ₦{item['expected']}")
                self.stdout.write(f"    Actual total credits: ₦{item['actual']}")
                self.stdout.write(
                    self.style.ERROR(
                        f"    OVERPAID BY: ₦{item['actual'] - item['expected']}"
                    )
                )
                self.stdout.write(f"    Number of credits: {item['credit_count']}")
                
                if item['tw_credits']:
                    self.stdout.write('    TaskWallet credits:')
                    for credit in item['tw_credits']:
                        self.stdout.write(f"      • ₦{credit['amount']} - {credit['created_at']} - {credit['description']}")
                
                if item['main_credits']:
                    self.stdout.write('    Main Wallet credits:')
                    for credit in item['main_credits']:
                        self.stdout.write(f"      • ₦{credit['amount']} - {credit['created_at']} - {credit['description']}")
        else:
            self.stdout.write(self.style.SUCCESS('✓ No overpayment issues found'))
        
        # 3. Summary
        self.stdout.write('\n\n' + '=' * 80)
        self.stdout.write(self.style.WARNING('SUMMARY'))
        self.stdout.write('=' * 80)
        
        total_tasks = Task.objects.count()
        total_escrows = EscrowTransaction.objects.count()
        
        self.stdout.write(f'\nTotal tasks: {total_tasks}')
        self.stdout.write(f'Total escrow transactions: {total_escrows}')
        self.stdout.write(f'Tasks with multiple escrows: {len(tasks_with_multiple_escrows)}')
        self.stdout.write(f'Submissions with overpayment: {len(problem_submissions)}')
        
        if tasks_with_multiple_escrows or problem_submissions:
            self.stdout.write(
                self.style.ERROR(
                    '\n⚠️  CRITICAL: Multiple escrow releases detected!'
                )
            )
            self.stdout.write(
                '\nRecommended actions:'
            )
            self.stdout.write('1. Remove signal-based escrow handling')
            self.stdout.write('2. Add unique constraints to prevent duplicate escrows')
            self.stdout.write('3. Run cleanup script to fix existing duplicates')
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ Escrow system looks healthy'))