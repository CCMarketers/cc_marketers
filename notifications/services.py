"""
notifications/services.py
Central helper used by signals (and anywhere else) to create a Notification
and push it through the WebSocket layer if the user is online.
"""
import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Notification

logger = logging.getLogger(__name__)


def _push_to_ws(notification: Notification) -> None:
    """Send notification payload to the user's personal WS group."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    group_name = f"notifications_{notification.recipient_id}"
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type":         "notify",
                "notification": notification.to_dict(),
            },
        )
    except Exception:
        logger.exception("WS push failed for notification %s", notification.id)


def create_notification(
    recipient,
    notif_type: str,
    title: str,
    message: str,
    link: str = "",
    push: bool = True,
) -> Notification:
    """
    Create and (optionally) push a notification.
    Always safe to call from Django signals (sync context).
    """
    notif = Notification.objects.create(
        recipient=recipient,
        notif_type=notif_type,
        title=title,
        message=message,
        link=link,
    )
    if push:
        _push_to_ws(notif)
    return notif