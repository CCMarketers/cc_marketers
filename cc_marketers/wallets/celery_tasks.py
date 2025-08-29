# wallets/celery_tasks.py - Background tasks using Celery
from celery import shared_task
from django.core.mail import send_mail
from django.contrib.auth.models import User
from .models import WithdrawalRequest, Transaction
from .services import WalletService
import logging

logger = logging.getLogger(__name__)

@shared_task
def send_transaction_notification(transaction_id):
    """Send email notification for transaction"""
    try:
        transaction = Transaction.objects.get(id=transaction_id)
        user = transaction.user
        
        subject = f'Wallet Transaction: {transaction.get_category_display()}'
        
        if transaction.transaction_type == 'credit':
            message = f'Your wallet has been credited with ${transaction.amount:.2f}'
        else:
            message = f'${transaction.amount:.2f} has been debited from your wallet'
        
        send_mail(
            subject=subject,
            message=message,
            from_email='noreply@yoursite.com',
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f'Transaction notification sent to {user.email}')
        
    except Transaction.DoesNotExist:
        logger.error(f'Transaction {transaction_id} not found')
    except Exception as e:
        logger.error(f'Failed to send transaction notification: {str(e)}')

@shared_task
def send_withdrawal_notification(withdrawal_id, status_changed_to):
    """Send email notification for withdrawal status change"""
    try:
        withdrawal = WithdrawalRequest.objects.get(id=withdrawal_id)
        user = withdrawal.user
        
        subject = f'Withdrawal Request {status_changed_to.title()}'
        
        if status_changed_to == 'approved':
            message = f'Your withdrawal request for ${withdrawal.amount:.2f} has been approved and will be processed shortly.'
        elif status_changed_to == 'rejected':
            message = f'Your withdrawal request for ${withdrawal.amount:.2f} has been rejected. Please contact support for details.'
        elif status_changed_to == 'completed':
            message = f'Your withdrawal of ${withdrawal.amount:.2f} has been completed and sent to your bank account.'
        else:
            message = f'Your withdrawal request status has been updated to: {status_changed_to}'
        
        send_mail(
            subject=subject,
            message=message,
            from_email='noreply@yoursite.com',
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f'Withdrawal notification sent to {user.email}')
        
    except WithdrawalRequest.DoesNotExist:
        logger.error(f'Withdrawal {withdrawal_id} not found')
    except Exception as e:
        logger.error(f'Failed to send withdrawal notification: {str(e)}')

@shared_task
def process_pending_withdrawals():
    """Background task to process pending withdrawals"""
    from django.core.management import call_command
    
    try:
        call_command('process_withdrawals', limit=50)
        logger.info('Pending withdrawals processed successfully')
    except Exception as e:
        logger.error(f'Failed to process pending withdrawals: {str(e)}')

@shared_task
def daily_wallet_audit():
    """Daily task to audit wallet balances"""
    from django.core.management import call_command
    
    try:
        call_command('sync_wallet_balances')
        logger.info('Daily wallet audit completed')
    except Exception as e:
        logger.error(f'Failed to run daily wallet audit: {str(e)}')
