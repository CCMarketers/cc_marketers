# In chat/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatRoom, Message
import asyncio

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.room_id = self.scope['url_route']['kwargs']['room_id']
            self.room_group_name = f'chat_{self.room_id}'
            self.user = self.scope.get('user')  # ✅ Use .get() to avoid KeyError
            
            # ✅ FIX 1: Check if user is authenticated FIRST
            if not self.user or not self.user.is_authenticated:
                print(f"Unauthenticated user tried to connect to room {self.room_id}")
                await self.close()
                return
            
            # ✅ FIX 2: Join group and accept connection BEFORE database queries
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            
            # Accept connection immediately
            await self.accept()
            
            # ✅ FIX 3: Verify access AFTER accepting (non-blocking)
            has_access = await self.verify_room_access()
            
            if not has_access:
                print(f"User {self.user.username} denied access to room {self.room_id}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Access denied to this chat room'
                }))
                await self.close()
                return
            
            # Send join notification only after verification
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_join',
                    'username': self.user.username
                }
            )
            
            print(f"User {self.user.username} connected to room {self.room_id}")
            
        except Exception as e:
            print(f"Error in WebSocket connect: {e}")
            await self.close()
 
    async def disconnect(self, close_code):
        try:
            # ✅ Fire and forget: don't block shutdown
            if hasattr(self, 'user') and self.user and self.user.is_authenticated:
                try:
                    asyncio.create_task(
                        self.channel_layer.group_send(
                            self.room_group_name,
                            {
                                'type': 'user_leave',
                                'username': self.user.username
                            }
                        )
                    )
                except Exception as e:
                    print(f"Error scheduling leave event: {e}")

            # ✅ Always discard the group cleanly
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

            print(f"User disconnected from room {self.room_id}")

        except Exception as e:
            print(f"Error in disconnect: {e}")


    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'message':
                message_content = data.get('message', '').strip()
                
                if message_content:
                    # Save message to database
                    message_data = await self.save_message(message_content)
                    
                    # Send message to room group
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'chat_message',
                            'message': message_content,
                            'sender': self.user.username,
                            'sender_id': str(self.user.id),
                            'timestamp': message_data['timestamp'],
                            'message_id': str(message_data['id'])
                        }
                    )
            
            elif message_type == 'typing':
                # Broadcast typing indicator
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'typing_indicator',
                        'user': self.user.username,
                        'is_typing': data.get('is_typing', False)
                    }
                )
                
        except json.JSONDecodeError:
            print("Invalid JSON received")
        except Exception as e:
            print(f"Error in receive: {e}")
    
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message': event['message'],
            'sender': event['sender'],
            'sender_id': str(event['sender_id']),
            'timestamp': event['timestamp']
        }))
    
    async def typing_indicator(self, event):
        # Send typing indicator to all except the sender
        if event['user'] != self.user.username:
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user': event['user'],
                'is_typing': event['is_typing']
            }))
    
    async def user_join(self, event):
        # Notify users when someone joins
        if event['username'] != self.user.username:
            await self.send(text_data=json.dumps({
                'type': 'user_join',
                'username': event['username']
            }))
    
    async def user_leave(self, event):
        # Notify users when someone leaves
        if event['username'] != self.user.username:
            await self.send(text_data=json.dumps({
                'type': 'user_leave',
                'username': event['username']
            }))
    
    @database_sync_to_async
    def verify_room_access(self):
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            return self.user.is_authenticated and (self.user == room.advertiser or self.user == room.worker)
        except ChatRoom.DoesNotExist:
            print(f"Room {self.room_id} does not exist")
            return False
        except Exception as e:
            print(f"Error verifying room access: {e}")
            return False
    
    @database_sync_to_async
    def save_message(self, content):
        from django.utils import timezone
        
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            message = Message.objects.create(
                chat_room=room,
                sender=self.user,
                content=content
            )
            
            # Update room's last_message_at
            room.last_message_at = timezone.now()
            room.save()
            
            return {
                'id': str(message.id),
                'timestamp': message.timestamp.isoformat()
            }
        except Exception as e:
            print(f"Error saving message: {e}")
            raise