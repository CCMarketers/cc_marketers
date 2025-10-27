from django.contrib import admin
from .models import ChatRoom, Message


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'advertiser', 'worker', 'created_at', 'last_message_at')
    list_filter = ('created_at', 'last_message_at')
    search_fields = ('advertiser__username', 'worker__username')
    readonly_fields = ('created_at', 'last_message_at')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'chat_room', 'timestamp', 'is_read', 'content_preview')
    list_filter = ('timestamp', 'is_read')
    search_fields = ('sender__username', 'content')
    readonly_fields = ('timestamp',)
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'