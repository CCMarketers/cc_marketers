
# wallets/management/commands/generate_wallet_report.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Sum, Count
from wallets.models import Wallet, Transaction, WithdrawalRequest
import csv

class Command(BaseCommand):
    help = 'Generate wallet system reports'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='wallet_report.csv',
            help='Output CSV file name',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to include in report',
        )
    
    def handle(self, *args, **options):
        output_file = options['output']
        days = options['days']
        
        end_date = timezone.now()
        start_date = end_date - timezone.timedelta(days=days)
        
        # Generate report data
        report_data = []
        
        # Overall stats
        total_users = Wallet.objects.count()
        total_balance = Wallet.objects.aggregate(Sum('balance'))['balance__sum'] or 0
        
        # Transaction stats
        period_transactions = Transaction.objects.filter(created_at__range=[start_date, end_date])
        total_transactions = period_transactions.count()
        total_credits = period_transactions.filter(transaction_type='credit').aggregate(Sum('amount'))['amount__sum'] or 0
        total_debits = period_transactions.filter(transaction_type='debit').aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Withdrawal stats
        period_withdrawals = WithdrawalRequest.objects.filter(created_at__range=[start_date, end_date])
        pending_withdrawals = period_withdrawals.filter(status='pending').count()
        approved_withdrawals = period_withdrawals.filter(status='approved').count()
        completed_withdrawals = period_withdrawals.filter(status='completed').count()
        
        # Write to CSV
        with open(output_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Header
            writer.writerow(['Wallet System Report', f'Period: {start_date.date()} to {end_date.date()}'])
            writer.writerow([])
            
            # Overall stats
            writer.writerow(['Overall Statistics'])
            writer.writerow(['Total Users with Wallets', total_users])
            writer.writerow(['Total System Balance', f'${total_balance:.2f}'])
            writer.writerow([])
            
            # Transaction stats
            writer.writerow(['Transaction Statistics (Period)'])
            writer.writerow(['Total Transactions', total_transactions])
            writer.writerow(['Total Credits', f'${total_credits:.2f}'])
            writer.writerow(['Total Debits', f'${total_debits:.2f}'])
            writer.writerow(['Net Flow', f'${(total_credits - total_debits):.2f}'])
            writer.writerow([])
            
            # Withdrawal stats
            writer.writerow(['Withdrawal Statistics (Period)'])
            writer.writerow(['Pending Requests', pending_withdrawals])
            writer.writerow(['Approved Requests', approved_withdrawals]) 
            writer.writerow(['Completed Requests', completed_withdrawals])
            
        self.stdout.write(
            self.style.SUCCESS(f'Report generated: {output_file}')
        )