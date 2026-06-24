"""
notifications/consumers.py
Each logged-in user joins their personal group "notifications_{user_id}".
The server pushes events; the client never needs to send anything.
"""
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.group_name = f"notifications_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.debug("WS connected: %s → %s", user.username, self.group_name)

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Called by channel layer when server pushes type="notify"
    async def notify(self, event):
        await self.send(text_data=json.dumps(event["notification"]))