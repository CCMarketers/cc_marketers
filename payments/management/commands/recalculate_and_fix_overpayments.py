# tasks/management/commands/recalculate_and_fix_overpayments.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from tasks.models import Submission, TaskWalletTransaction
from payments.models import PaymentTransaction as Transaction
from decimal import Decimal
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Recalculate payments and fix overpayments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--fix-overpayments',
            action='store_true',
            help='Debit excess payments from users',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        fix_overpayments = options['fix_overpayments']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE\n'))
        
        self.stdout.write('📊 Analyzing all approved submissions...\n')
        
        approved_submissions = Submission.objects.filter(
            status='approved'
        ).select_related('task', 'member', 'reviewed_by')
        
        overpayments = []
        correct_payments = []
        underpayments = []
        
        for submission in approved_submissions:
            expected_payment = submission.task.payout_per_slot * Decimal('0.80')  # 80% after platform cut
            
            # Find all credits around submission approval time
            if submission.reviewed_at:
                time_start = submission.reviewed_at - timedelta(hours=1)
                time_end = submission.reviewed_at + timedelta(hours=1)
            else:
                time_start = submission.submitted_at
                time_end = submission.submitted_at + timedelta(days=1)
            
            # Check TaskWallet
            tw_credits = TaskWalletTransaction.objects.filter(
                user=submission.member,
                transaction_type='credit',
                created_at__range=(time_start, time_end)
            ).exclude(category__in=['topup_from_main', 'admin_adjustment'])
            
            # Check Main Wallet
            main_credits = Transaction.objects.filter(
                user=submission.member,
                transaction_type='credit',
                category='task_payment',
                created_at__range=(time_start, time_end)
            )
            
            total_received = (
                (tw_credits.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')) +
                (main_credits.aggregate(Sum('amount_usd'))['amount_usd__sum'] or Decimal('0'))
            )
            
            difference = total_received - expected_payment
            
            if abs(difference) < Decimal('0.01'):  # Within 1 cent tolerance
                correct_payments.append({
                    'submission': submission,
                    'expected': expected_payment,
                    'received': total_received
                })
            elif difference > Decimal('0.01'):  # Overpaid
                overpayments.append({
                    'submission': submission,
                    'expected': expected_payment,
                    'received': total_received,
                    'excess': difference,
                    'tw_credits': list(tw_credits.values('id', 'amount', 'created_at')),
                    'main_credits': list(main_credits.values('id', 'amount_usd', 'created_at'))
                })
            else:  # Underpaid
                underpayments.append({
                    'submission': submission,
                    'expected': expected_payment,
                    'received': total_received,
                    'shortage': abs(difference)
                })
        
        # ========== REPORT ==========
        
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.WARNING('PAYMENT ANALYSIS REPORT'))
        self.stdout.write('=' * 80)
        
        self.stdout.write(f'\n✓ Correct payments: {len(correct_payments)}')
        self.stdout.write(f'❌ Overpayments: {len(overpayments)}')
        self.stdout.write(f'⚠️  Underpayments: {len(underpayments)}')
        
        if overpayments:
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write(self.style.ERROR('OVERPAYMENTS DETAIL'))
            self.stdout.write('=' * 80)
            
            total_excess = Decimal('0')
            
            for item in overpayments:
                submission = item['submission']
                self.stdout.write(
                    f"\n  Submission #{submission.id} - {submission.member.username}"
                )
                self.stdout.write(f"    Task: {submission.task.title[:50]}")
                self.stdout.write(f"    Payout per slot: ₦{submission.task.payout_per_slot}")
                self.stdout.write(f"    Expected (80%): ₦{item['expected']}")
                self.stdout.write(f"    Actually received: ₦{item['received']}")
                self.stdout.write(
                    self.style.ERROR(f"    EXCESS: ₦{item['excess']}")
                )
                
                if item['tw_credits']:
                    self.stdout.write('    TaskWallet credits:')
                    for credit in item['tw_credits']:
                        self.stdout.write(f"      • ₦{credit['amount']} - {credit['created_at']}")
                
                if item['main_credits']:
                    self.stdout.write('    Main Wallet credits:')
                    for credit in item['main_credits']:
                        self.stdout.write(f"      • ₦{credit['amount_usd']} - {credit['created_at']}")
                
                total_excess += item['excess']
            
            self.stdout.write(f'\n  TOTAL EXCESS PAID OUT: ₦{total_excess}')
        
        if underpayments:
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write(self.style.WARNING('UNDERPAYMENTS DETAIL'))
            self.stdout.write('=' * 80)
            
            total_shortage = Decimal('0')
            
            for item in underpayments:
                submission = item['submission']
                self.stdout.write(
                    f"\n  Submission #{submission.id} - {submission.member.username}"
                )
                self.stdout.write(f"    Expected: ₦{item['expected']}")
                self.stdout.write(f"    Received: ₦{item['received']}")
                self.stdout.write(
                    self.style.WARNING(f"    SHORTAGE: ₦{item['shortage']}")
                )
                total_shortage += item['shortage']
            
            self.stdout.write(f'\n  TOTAL SHORTAGE: ₦{total_shortage}')
        
        # ========== FIX OVERPAYMENTS ==========
        
        if fix_overpayments and overpayments and not dry_run:
            self.stdout.write('\n' + '=' * 80)
            self.stdout.write(self.style.WARNING('FIXING OVERPAYMENTS'))
            self.stdout.write('=' * 80)
            
            fixed_count = 0
            fixed_amount = Decimal('0')
            
            for item in overpayments:
                submission = item['submission']
                user = submission.member
                excess = item['excess']
                
                try:
                    with transaction.atomic():
                        from wallets.services import WalletService
                        
                        # Check user's current balance
                        wallet = WalletService.get_or_create_wallet(user)
                        
                        if wallet.balance < excess:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  ⚠️  {user.username}: Insufficient balance to debit "
                                    f"(has ₦{wallet.balance}, needs ₦{excess}). Skipping."
                                )
                            )
                            continue
                        
                        # Debit excess from Main Wallet
                        WalletService.debit_wallet(
                            user=user,
                            amount=excess,
                            category="correction",
                            description=f"Overpayment correction for Submission #{submission.id}",
                            reference=f"OVERPAYMENT_CORRECTION_{submission.id}"
                        )
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✓ {user.username}: Debited ₦{excess} excess payment"
                            )
                        )
                        
                        fixed_count += 1
                        fixed_amount += excess
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ❌ {user.username}: Error - {str(e)}"
                        )
                    )
                    logger.error(f"Error fixing overpayment for submission {submission.id}: {e}")
            
            self.stdout.write(f'\n  Fixed {fixed_count} overpayments, recovered ₦{fixed_amount}')
        
        elif fix_overpayments and overpayments and dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  Run without --dry-run to debit excess payments'
                )
            )
        
        # ========== SUMMARY ==========
        
        self.stdout.write('\n' + '=' * 80)
        self.stdout.write(self.style.WARNING('RECOMMENDATIONS'))
        self.stdout.write('=' * 80)
        
        if overpayments:
            self.stdout.write('\n1. Apply code fixes to prevent future overpayments:')
            self.stdout.write('   - Remove signal-based escrow handling')
            self.stdout.write('   - Add database constraints')
            self.stdout.write('   - Update release_task_escrow() with duplicate checks')
            
            self.stdout.write('\n2. Fix existing overpayments:')
            self.stdout.write('   python manage.py recalculate_and_fix_overpayments --fix-overpayments')
            
            self.stdout.write('\n3. Verify fixes:')
            self.stdout.write('   python manage.py debug_escrow_releases')
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ No overpayments found!'))
        
        self.stdout.write('\n')