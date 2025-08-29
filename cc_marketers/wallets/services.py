# wallets/services.py
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from .models import Wallet, Transaction, EscrowTransaction, WithdrawalRequest
import uuid
from referrals.models import ReferralEarning
from tasks.models import TaskWalletTransaction



class WalletService:
    """Handle all wallet operations with proper double-entry bookkeeping"""
    
    @staticmethod
    def get_or_create_wallet(user):
        """Get or create wallet for user"""
        wallet, created = Wallet.objects.get_or_create(user=user)
        return wallet

    @staticmethod
    @transaction.atomic
    def credit_wallet(user, amount, category, description="", reference=None, task=None):
        """Credit user's wallet with proper transaction logging"""
        wallet = WalletService.get_or_create_wallet(user)
        
        # Create transaction record
        txn = Transaction.objects.create(
            user=user,
            transaction_type='credit',
            category=category,
            amount=amount,
            balance_before=wallet.balance,
            balance_after=wallet.balance + amount,
            status='success',
            reference=reference or str(uuid.uuid4()),
            description=description,
            task=task
        )
        
        # Update wallet balance
        wallet.balance += amount
        wallet.save()
        
        return txn

    @staticmethod
    @transaction.atomic
    def debit_wallet(user, amount, category, description="", reference=None, task=None):
        """Debit user's wallet with proper transaction logging"""
        wallet = WalletService.get_or_create_wallet(user)
        
        # Check if user has sufficient balance
        if category == 'escrow':
            available_balance = wallet.get_available_balance()
        else:
            available_balance = wallet.balance
            
        if available_balance < amount:
            raise ValueError(f"Insufficient balance. Available: ${available_balance}, Required: ${amount}")
        
        # Create transaction record
        txn = Transaction.objects.create(
            user=user,
            transaction_type='debit',
            category=category,
            amount=amount,
            balance_before=wallet.balance,
            balance_after=wallet.balance - amount,
            status='success',
            reference=reference or str(uuid.uuid4()),
            description=description,
            task=task
        )
        
        # Update wallet balance
        wallet.balance -= amount
        wallet.save()
        
        return txn

    @staticmethod
    @transaction.atomic
    def create_task_escrow(user, task, amount):
        """Lock funds in EscrowTransaction from TaskWallet when advertiser creates a task."""
        from tasks.services import TaskWalletService 
        wallet = TaskWalletService.get_or_create_wallet(user)
        amount = Decimal(amount)

        if wallet.balance < amount:
            raise ValueError(
                f"Insufficient TaskWallet balance. "
                f"Available: {wallet.balance}, Required: {amount}"
            )

        # Debit TaskWallet
        before = wallet.balance
        wallet.balance -= amount
        wallet.save()

        txn = TaskWalletTransaction.objects.create(
            user=user,
            transaction_type="debit",
            category="task_posting",
            amount=amount,
            balance_before=before,
            balance_after=wallet.balance,
            description=f"Escrow for task: {task.title}",
        )

        # Create Escrow record linked to TaskWalletTransaction (NOT Main Wallet)
        escrow = EscrowTransaction.objects.create(
            task=task,
            advertiser=user,
            amount=amount,
            taskwallet_transaction=txn,  # 👈 link to TaskWalletTransaction
            status="locked",
        )

        return escrow
    
    @staticmethod
    @transaction.atomic
    def release_escrow_to_member(task, member):
        """Release escrowed funds to task member upon approval (with 20% company fee)"""
        from django.conf import settings
        from django.contrib.auth import get_user_model

        User = get_user_model()

        try:
            escrow = EscrowTransaction.objects.get(task=task, status='locked')

            # ✅ Split amount
            company_cut = (escrow.amount * Decimal("0.20")).quantize(Decimal("0.01"))
            member_amount = escrow.amount - company_cut

            # ✅ Fetch system/company user
            company_user = User.objects.get(username=settings.COMPANY_SYSTEM_USERNAME)

            # 💰 Pay worker
            member_txn = WalletService.credit_wallet(
                user=member,
                amount=member_amount,
                category="task_earning",
                description=f"Payment for completed task: {task.title}",
                reference=f"TASK_PAYMENT_{task.id}",
                task=task,
            )

            # 💰 Pay company
            WalletService.credit_wallet(
                user=company_user,
                amount=company_cut,
                category="platform_fee",
                description=f"20% platform fee for task: {task.title}",
                reference=f"FEE_TASK_{task.id}",
                task=task,
            )

            # 🔄 Update escrow status
            escrow.status = "released"
            escrow.released_at = timezone.now()
            escrow.save()

            # 🔄 Update linked TaskWalletTransaction
            escrow.taskwallet_transaction.status = "success"
            escrow.taskwallet_transaction.save()

            return member_txn

        except EscrowTransaction.DoesNotExist:
            raise ValueError("No locked escrow found for this task")


    @staticmethod
    @transaction.atomic
    def refund_escrow_to_advertiser(task):
        """Refund escrowed funds back to advertiser upon rejection"""
        try:
            escrow = EscrowTransaction.objects.get(task=task, status='locked')
            
            # Credit advertiser's wallet (refund)
            credit_txn = WalletService.credit_wallet(
                user=escrow.advertiser,
                amount=escrow.amount,
                category='refund',
                description=f"Refund for task: {task.title}",
                reference=f"REFUND_TASK_{task.id}",
                task=task
            )
            
            # Update escrow status
            escrow.status = "refunded"
            escrow.released_at = timezone.now()
            escrow.save()

            # ✅ Update linked TaskWalletTransaction
            escrow.taskwallet_transaction.status = "failed"   # refund means debit didn’t hold
            escrow.taskwallet_transaction.save()

            
            return credit_txn
            
        except EscrowTransaction.DoesNotExist:
            raise ValueError("No locked escrow found for this task")

    @staticmethod
    @transaction.atomic
    def process_referral_bonus(referrer, referred, amount=Decimal('10.00')):
        """Process referral bonus when someone signs up via referral"""
        # Credit referrer's wallet
        credit_txn = WalletService.credit_wallet(
            user=referrer,
            amount=amount,
            category='referral_bonus',
            description=f"Referral bonus for {referred.username}",
            reference=f"REFERRAL_{referred.id}"
        )
        
        # Create referral earning record
        referral = ReferralEarning.objects.create(
            referrer=referrer,
            referred=referred,
            amount=amount,
            transaction=credit_txn
        )
        
        return referral

    @staticmethod
    @transaction.atomic
    def create_withdrawal_request(user, amount, withdrawal_method, account_details):
        """Create a withdrawal request"""
        wallet = WalletService.get_or_create_wallet(user)

        # ✅ Minimum withdrawal check
        if amount < Decimal("10.00"):
            raise ValueError("Minimum withdrawal amount is $10.")

        # ✅ Check if user has sufficient balance
        if wallet.balance < amount:
            raise ValueError(f"Insufficient balance. Available: ${wallet.balance}, Required: ${amount}")

        # Create withdrawal request
        withdrawal = WithdrawalRequest.objects.create(
            user=user,
            amount=amount,
            withdrawal_method=withdrawal_method,
            account_number=account_details.get('account_number', ''),
            account_name=account_details.get('account_name', ''),
            bank_name=account_details.get('bank_name', ''),
            bank_code=account_details.get('bank_code', ''),
            status='pending'
        )

        return withdrawal

    @staticmethod
    @transaction.atomic
    def approve_withdrawal(withdrawal_id, admin_user, gateway_reference=None):
        """Approve withdrawal request and debit user's wallet"""
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        
        if withdrawal.status != 'pending':
            raise ValueError("Withdrawal request is not pending")
        
        # Debit user's wallet
        debit_txn = WalletService.debit_wallet(
            user=withdrawal.user,
            amount=withdrawal.amount,
            category='withdrawal',
            description=f"Withdrawal request #{withdrawal.id}",
            reference=f"WITHDRAWAL_{withdrawal.id}"
        )
        
        # Update withdrawal request
        withdrawal.status = 'approved'
        withdrawal.processed_by = admin_user
        withdrawal.processed_at = timezone.now()
        withdrawal.transaction = debit_txn
        withdrawal.gateway_reference = gateway_reference or ""
        withdrawal.save()
        
        return withdrawal

    @staticmethod
    @transaction.atomic
    def reject_withdrawal(withdrawal_id, admin_user, reason=""):
        """Reject withdrawal request"""
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        
        if withdrawal.status != 'pending':
            raise ValueError("Withdrawal request is not pending")
        
        withdrawal.status = 'rejected'
        withdrawal.processed_by = admin_user
        withdrawal.processed_at = timezone.now()
        withdrawal.admin_notes = reason
        withdrawal.save()
        
        return withdrawal