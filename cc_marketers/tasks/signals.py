# tasks/signals.py - Integration with existing tasks app
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Task, TaskSubmission  # Assuming these exist in your tasks app
from wallets.services import WalletService
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Task)
def handle_task_creation(sender, instance, created, **kwargs):
    """When a task is created, lock funds in escrow"""
    if created and instance.reward_amount:
        try:
            # Create escrow transaction
            WalletService.create_task_escrow(
                advertiser=instance.advertiser,  # Assuming Task has advertiser field
                task=instance,
                amount=instance.reward_amount  # Assuming Task has reward_amount field
            )
            logger.info(f"Escrow created for task {instance.id}: ${instance.reward_amount}")
            
        except ValueError as e:
            logger.error(f"Failed to create escrow for task {instance.id}: {str(e)}")
            # Optionally, you could set task status to 'insufficient_funds' or similar
            instance.status = 'insufficient_funds'
            instance.save()

@receiver(post_save, sender=TaskSubmission)
def handle_task_submission_approval(sender, instance, created, **kwargs):
    """When a task submission is approved, release escrow funds to member"""
    if not created and hasattr(instance, 'status'):
        
        # Task approved - release escrow to member
        if instance.status == 'approved' and hasattr(instance, 'previous_status'):
            if instance.previous_status != 'approved':
                try:
                    WalletService.release_escrow_to_member(
                        task=instance.task,
                        member=instance.member  # Assuming TaskSubmission has member field
                    )
                    logger.info(f"Escrow released for task {instance.task.id} to {instance.member.username}")
                    
                except ValueError as e:
                    logger.error(f"Failed to release escrow for task {instance.task.id}: {str(e)}")
        
        # Task rejected - refund escrow to advertiser
        elif instance.status == 'rejected' and hasattr(instance, 'previous_status'):
            if instance.previous_status != 'rejected':
                try:
                    WalletService.refund_escrow_to_advertiser(task=instance.task)
                    logger.info(f"Escrow refunded for task {instance.task.id}")
                    
                except ValueError as e:
                    logger.error(f"Failed to refund escrow for task {instance.task.id}: {str(e)}")

@receiver(pre_save, sender=TaskSubmission)
def store_previous_status(sender, instance, **kwargs):
    """Store previous status to detect changes"""
    if instance.pk:
        try:
            previous = TaskSubmission.objects.get(pk=instance.pk)
            instance.previous_status = previous.status
        except TaskSubmission.DoesNotExist:
            instance.previous_status = None
