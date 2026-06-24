"""
notifications/signals.py
Connect to existing models via post_save signals.
AppConfig.ready() in notifications/apps.py imports this module.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy imports inside handlers to avoid circular imports at startup
# ---------------------------------------------------------------------------

def _notif_service():
    from .services import create_notification
    return create_notification


# ── 1. Chat messages ────────────────────────────────────────────────────────
@receiver(post_save, sender="chat.Message")
def on_new_chat_message(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        room = instance.chat_room
        recipient = (
            room.worker if instance.sender == room.advertiser else room.advertiser
        )
        if recipient == instance.sender:
            return
        _notif_service()(
            recipient=recipient,
            notif_type="chat_message",
            title="New message",
            message=f"{instance.sender.username}: {instance.content[:80]}",
            link=reverse("chat:room", kwargs={"room_id": room.id}),
        )
    except Exception:
        logger.exception("Signal error: on_new_chat_message")


# ── 2. Submission status changes (approved / rejected) ──────────────────────
@receiver(post_save, sender="tasks.Submission")
def on_submission_status_change(sender, instance, created, **kwargs):
    if created:
        # Notify advertiser of new submission
        try:
            _notif_service()(
                recipient=instance.task.advertiser,
                notif_type="new_submission",
                title="New submission",
                message=(
                    f"{instance.member.username} submitted to '{instance.task.title}'"
                ),
                link=reverse(
                    "tasks:review_submissions",
                    kwargs={"task_id": instance.task.id},
                ),
            )
        except Exception:
            logger.exception("Signal error: on_submission_status_change (created)")
        return

    # Status changed on an existing submission — notify the worker
    if instance.status in ("approved", "rejected"):
        try:
            notif_type = (
                "submission_approved" if instance.status == "approved"
                else "submission_rejected"
            )
            title = (
                "Submission approved 🎉" if instance.status == "approved"
                else "Submission rejected"
            )
            message = (
                f"Your submission for '{instance.task.title}' was {instance.status}."
            )
            if instance.status == "rejected" and instance.rejection_reason:
                message += f" Reason: {instance.rejection_reason}"

            _notif_service()(
                recipient=instance.member,
                notif_type=notif_type,
                title=title,
                message=message,
                link=reverse("tasks:my_submissions"),
            )
        except Exception:
            logger.exception("Signal error: on_submission_status_change (status)")


# ── 3. Wallet credited (PaymentTransaction success) ─────────────────────────
@receiver(post_save, sender="payments.PaymentTransaction")
def on_payment_transaction(sender, instance, created, **kwargs):
    try:
        from payments.models import PaymentTransaction
        if instance.status != PaymentTransaction.Status.SUCCESS:
            return

        if instance.transaction_type == PaymentTransaction.TransactionType.FUNDING:
            _notif_service()(
                recipient=instance.user,
                notif_type="wallet_credit",
                title="Wallet credited",
                message=f"₦{instance.amount_usd} has been added to your wallet.",
                link=reverse("wallets:dashboard"),
            )
        elif instance.transaction_type == PaymentTransaction.TransactionType.WITHDRAWAL:
            _notif_service()(
                recipient=instance.user,
                notif_type="wallet_withdrawal",
                title="Withdrawal processed",
                message=f"Your withdrawal of ₦{instance.amount_usd} was successful.",
                link=reverse("wallets:dashboard"),
            )
    except Exception:
        logger.exception("Signal error: on_payment_transaction")


# ── 4. Referral signup ───────────────────────────────────────────────────────
@receiver(post_save, sender="referrals.Referral")
def on_new_referral(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        _notif_service()(
            recipient=instance.referrer,
            notif_type="referral_signup",
            title="New referral!",
            message=(
                f"{instance.referred.username} just signed up using your referral link."
            ),
            link=reverse("referrals:dashboard"),
        )
    except Exception:
        logger.exception("Signal error: on_new_referral")