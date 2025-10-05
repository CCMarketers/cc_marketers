# tasks/signals.py
import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Task, Submission  # use real models
from .services import TaskWalletService  # your escrow service

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Task)
def handle_task_creation(sender, instance, created, **kwargs):
    """
    When a task is created, lock advertiser funds in escrow.
    Uses TaskWalletService.create_task_escrow
    """
    if created:
        # We don't have a reward_amount field; use total_payout
        amount = instance.total_payout
        try:
            TaskWalletService.create_task_escrow(
                advertiser=instance.advertiser,
                task=instance,
                amount=amount,
            )
            logger.info(f"Escrow created for Task {instance.pk}: ${amount}")
        except ValueError as e:
            logger.error(f"Failed to create escrow for Task {instance.pk}: {str(e)}")
            # Optionally mark status
            instance.status = "insufficient_funds"
            instance.save(update_fields=["status"])


@receiver(pre_save, sender=Submission)
def store_previous_status(sender, instance, **kwargs):
    """
    Store previous status to detect changes on update.
    """
    if instance.pk:
        try:
            previous = Submission.objects.get(pk=instance.pk)
            instance.previous_status = previous.status
        except Submission.DoesNotExist:
            instance.previous_status = None


@receiver(post_save, sender=Submission)
def handle_submission_status_change(sender, instance, created, **kwargs):
    """
    When a submission is approved or rejected, release or refund escrow.
    """
    # Only handle status changes on existing records
    if created or not hasattr(instance, "previous_status"):
        return

    # APPROVED → release escrow to member
    if instance.status == "approved" and instance.previous_status != "approved":
        try:
            # You need to locate the EscrowTransaction for this task
            escrow = instance.task.escrowtransaction_set.filter(status="locked").first()
            if escrow:
                TaskWalletService.release_task_escrow(escrow, member=instance.member)
                logger.info(
                    f"Escrow released for Task {instance.task.pk} to {instance.member.username}"
                )
        except ValueError as e:
            logger.error(
                f"Failed to release escrow for Task {instance.task.pk}: {str(e)}"
            )

    # REJECTED → refund escrow to advertiser
    elif instance.status == "rejected" and instance.previous_status != "rejected":
        try:
            escrow = instance.task.escrowtransaction_set.filter(status="locked").first()
            if escrow:
                TaskWalletService.refund_task_escrow(escrow)
                logger.info(f"Escrow refunded for Task {instance.task.pk}")
        except ValueError as e:
            logger.error(
                f"Failed to refund escrow for Task {instance.task.pk}: {str(e)}"
            )
