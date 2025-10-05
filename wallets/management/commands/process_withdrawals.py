
# wallets/management/commands/process_withdrawals.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from wallets.models import WithdrawalRequest
from wallets.services import WalletService
import requests
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process approved withdrawal requests via payment gateway'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without actually processing payments',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of withdrawals to process',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        limit = options['limit']
        
        # Get approved withdrawals that haven't been processed
        withdrawals = WithdrawalRequest.objects.filter(
            status='approved'
        ).order_by('created_at')[:limit]
        
        if not withdrawals:
            self.stdout.write(self.style.WARNING('No approved withdrawals to process'))
            return
        
        processed_count = 0
        failed_count = 0
        
        for withdrawal in withdrawals:
            try:
                if dry_run:
                    self.stdout.write(
                        f'[DRY RUN] Would process withdrawal {withdrawal.id} for ${withdrawal.amount}'
                    )
                else:
                    # Process payment via gateway (Paystack example)
                    success = self.process_payment(withdrawal)
                    
                    if success:
                        withdrawal.status = 'completed'
                        withdrawal.save()
                        processed_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'Processed withdrawal {withdrawal.id}')
                        )
                    else:
                        withdrawal.status = 'failed'
                        withdrawal.admin_notes += f'\nPayment failed: {timezone.now()}'
                        withdrawal.save()
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(f'Failed to process withdrawal {withdrawal.id}')
                        )
                        
            except Exception as e:
                logger.error(f'Error processing withdrawal {withdrawal.id}: {str(e)}')
                failed_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Processing complete: {processed_count} succeeded, {failed_count} failed'
            )
        )
    
    def process_payment(self, withdrawal):
        """Process payment via Paystack or Flutterwave"""
        # This is a simplified example - implement based on your chosen gateway
        
        if withdrawal.withdrawal_method == 'paystack':
            return self.process_paystack_transfer(withdrawal)
        elif withdrawal.withdrawal_method == 'flutterwave':
            return self.process_flutterwave_transfer(withdrawal)
        
        return False
    
    def process_paystack_transfer(self, withdrawal):
        """Process transfer via Paystack"""
        from django.conf import settings
        
        url = "https://api.paystack.co/transfer"
        headers = {
            'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
            'Content-Type': 'application/json',
        }
        
        # First, create transfer recipient
        recipient_data = {
            "type": "nuban",
            "name": withdrawal.account_name,
            "account_number": withdrawal.account_number,
            "bank_code": withdrawal.bank_code,
            "currency": "NGN"
        }
        
        recipient_response = requests.post(
            "https://api.paystack.co/transferrecipient",
            json=recipient_data,
            headers=headers
        )
        
        if recipient_response.status_code != 201:
            return False
        
        recipient_code = recipient_response.json()['data']['recipient_code']
        
        # Create transfer
        transfer_data = {
            "source": "balance",
            "amount": int(withdrawal.amount * 100),  # Convert to kobo
            "recipient": recipient_code,
            "reason": f"Withdrawal for user {withdrawal.user.username}",
            "reference": str(withdrawal.id)
        }
        
        transfer_response = requests.post(url, json=transfer_data, headers=headers)
        
        if transfer_response.status_code == 200:
            response_data = transfer_response.json()
            withdrawal.gateway_reference = response_data['data']['reference']
            withdrawal.gateway_response = response_data
            withdrawal.save()
            return True
        
        return False
    
    def process_flutterwave_transfer(self, withdrawal):
        """Process transfer via Flutterwave"""
        # Implement Flutterwave transfer logic here
        return False

# wallets/management/commands/sync_wallet_balances.py
from django.core.management.base import BaseCommand
from django.db.models import Sum
from wallets.models import Wallet, Transaction
from decimal import Decimal

class Command(BaseCommand):
    help = 'Sync wallet balances with transaction history (audit/fix balances)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Actually fix incorrect balances',
        )
    
    def handle(self, *args, **options):
        fix_balances = options['fix']
        
        wallets = Wallet.objects.all()
        incorrect_count = 0
        
        for wallet in wallets:
            # Calculate balance from transactions
            credits = Transaction.objects.filter(
                user=wallet.user,
                transaction_type='credit',
                status='success'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            debits = Transaction.objects.filter(
                user=wallet.user,
                transaction_type='debit',
                status='success'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            calculated_balance = credits - debits
            
            if wallet.balance != calculated_balance:
                incorrect_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'User {wallet.user.username}: Wallet=${wallet.balance}, '
                        f'Calculated=${calculated_balance}, Difference=${wallet.balance - calculated_balance}'
                    )
                )
                
                if fix_balances:
                    wallet.balance = calculated_balance
                    wallet.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'Fixed balance for {wallet.user.username}')
                    )
        
        if incorrect_count == 0:
            self.stdout.write(self.style.SUCCESS('All wallet balances are correct!'))
        else:
            if fix_balances:
                self.stdout.write(
                    self.style.SUCCESS(f'Fixed {incorrect_count} incorrect balances')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Found {incorrect_count} incorrect balances. Use --fix to correct them.'
                    )
                )
