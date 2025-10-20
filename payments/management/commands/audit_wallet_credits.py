# tasks/management/commands/audit_wallet_credits.py

from django.core.management.base import BaseCommand
from django.db.models import Sum, Q
from tasks.models import TaskWalletTransaction
from wallets.models import  EscrowTransaction
from payments.models import PaymentTransaction as Transaction
from decimal import Decimal

class Command(BaseCommand):
    help = 'Audit wallet credits to identify incorrect TaskWallet credits'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('WALLET CREDIT AUDIT REPORT'))
        self.stdout.write(self.style.WARNING('=' * 80))
        
        # 1. Find TaskWallet credits that should be in Main Wallet
        task_wallet_earnings = TaskWalletTransaction.objects.filter(
            transaction_type="credit",
            category__in=["task_payment", ""]  # empty category is suspicious
        ).exclude(
            category__in=["topup_from_main", "admin_adjustment", "subscription_bonus"]
        )
        
        self.stdout.write(f'\n📊 Found {task_wallet_earnings.count()} TaskWallet earnings credits')
        
        # Group by user
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        users_with_wrong_credits = {}
        
        for txn in task_wallet_earnings:
            user = txn.user
            if user.username not in users_with_wrong_credits:
                users_with_wrong_credits[user.username] = {
                    'user': user,
                    'transactions': [],
                    'total': Decimal('0')
                }
            
            users_with_wrong_credits[user.username]['transactions'].append(txn)
            users_with_wrong_credits[user.username]['total'] += txn.amount
        
        # Display report
        self.stdout.write(f'\n🔴 {len(users_with_wrong_credits)} users have incorrect TaskWallet credits:\n')
        
        for username, data in sorted(users_with_wrong_credits.items(), 
                                     key=lambda x: x[1]['total'], reverse=True):
            self.stdout.write(
                f"  • {username}: ₦{data['total']} "
                f"({len(data['transactions'])} transactions)"
            )
        
        # 2. Check Main Wallet for correct credits
        self.stdout.write(f'\n\n📊 Checking Main Wallet credits...')
        
        main_wallet_earnings = Transaction.objects.filter(
            transaction_type="credit",
            category="task_payment"
        )
        
        self.stdout.write(f'✓ Found {main_wallet_earnings.count()} correct Main Wallet earnings')
        
        # 3. Analyze escrow releases
        self.stdout.write(f'\n\n📊 Analyzing escrow releases...')
        
        released_escrows = EscrowTransaction.objects.filter(status="released")
        total_released = released_escrows.aggregate(Sum('amount_usd'))['amount_usd__sum'] or 0
        
        self.stdout.write(f'✓ {released_escrows.count()} escrows released')
        self.stdout.write(f'✓ Total released: ₦{total_released}')
        
        # Calculate expected vs actual
        expected_main_wallet = total_released * Decimal('0.80')  # 80% to workers
        actual_main_wallet = (
            main_wallet_earnings.aggregate(Sum('amount_usd'))['amount_usd__sum'] or Decimal('0')
        )

        
        self.stdout.write(f'\n📈 Expected Main Wallet credits: ₦{expected_main_wallet}')
        self.stdout.write(f'📉 Actual Main Wallet credits: ₦{actual_main_wallet}')
        
        discrepancy = expected_main_wallet - actual_main_wallet
        
        if discrepancy > 0:
            self.stdout.write(
                self.style.ERROR(
                    f'\n❌ DISCREPANCY: ₦{discrepancy} missing from Main Wallets!'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    '   This amount is likely credited to TaskWallets instead.'
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ No discrepancy found'))
        
        # 4. Recommendations
        self.stdout.write(f'\n\n' + '=' * 80)
        self.stdout.write(self.style.WARNING('RECOMMENDATIONS:'))
        self.stdout.write('=' * 80)
        
        if len(users_with_wrong_credits) > 0:
            self.stdout.write(
                '\n1. Run migration to move TaskWallet earnings → Main Wallet'
            )
            self.stdout.write(
                '   python manage.py fix_wallet_credits --dry-run'
            )
            self.stdout.write(
                '\n2. Deploy fixed release_task_escrow() code'
            )
            self.stdout.write(
                '\n3. Monitor future escrow releases'
            )
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ No action needed'))
        
        self.stdout.write('\n')