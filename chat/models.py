# ============================================================================
# STEP 5: CHAT APP MODELS (chat/models.py)
# ============================================================================

from django.db import models
from django.conf import settings



class ChatRoom(models.Model):
    """
    Represents a unique chat room between an advertiser and a worker.
    Only one room should exist per advertiser-worker pair.
    """
    advertiser = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='advertiser_rooms'
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='worker_rooms'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('advertiser', 'worker')
        ordering = ['-last_message_at']
    
    def __str__(self):
        return f"Chat: {self.advertiser.username} ↔ {self.worker.username}"
    
    def get_other_user(self, current_user):
        """Get the other participant in the chat"""
        if current_user == self.advertiser:
            return self.worker
        return self.advertiser
    
    def unread_count(self, user):
        """Get unread message count for a specific user"""
        return self.messages.filter(is_read=False).exclude(sender=user).count()


class Message(models.Model):
    """
    Individual messages within a chat room.
    """
    chat_room = models.ForeignKey(
        ChatRoom, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='sent_messages'
    )
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['timestamp']
    
    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"