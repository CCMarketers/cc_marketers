from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from .models import ChatRoom, Message
from tasks.models import Task


def chat_room_list(request):
    """List all chat rooms for the current user"""
    rooms = (
        ChatRoom.objects.filter(
            Q(advertiser=request.user) | Q(worker=request.user)
        )
        .select_related('advertiser', 'worker')
        .prefetch_related('messages')
    )

    # Add a custom attribute: task_count (number of shared tasks)
    for room in rooms:
        room.task_count = Task.objects.filter(
            Q(advertiser=room.advertiser, submissions__member=room.worker)
            | Q(advertiser=room.worker, submissions__member=room.advertiser)
        ).distinct().count()

    context = {
        'rooms': rooms,
    }
    return render(request, 'chat/room_list.html', context)


@login_required
def chat_room(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id)
    
    if request.user not in [room.advertiser, room.worker]:
        return redirect('chat:room_list')
    
    messages = room.messages.select_related('sender').all()
    advertiser = room.advertiser
    worker = room.worker

    # ✅ Get all tasks done between these two users
    tasks = Task.objects.filter(
        Q(advertiser=advertiser, submissions__member=worker) |
        Q(advertiser=worker, submissions__member=advertiser)
    ).distinct().order_by('-created_at')

    
    # Mark messages as read
    Message.objects.filter(
        chat_room=room,
        is_read=False
    ).exclude(sender=request.user).update(is_read=True)
    
    context = {
        'room': room,
        'room_name': str(room.id), 
        'messages': messages,
        'tasks': tasks,
        'other_user': room.get_other_user(request.user)
    }
    return render(request, 'chat/chat_room.html', context)


@login_required
def get_or_create_room(request, user_id):
    '''
    Get or create a chat room between current user and another user.
    Useful for creating rooms when tasks are completed.
    '''
    from django.contrib.auth.models import User
    
    other_user = get_object_or_404(User, id=user_id)
    
    # Determine who is advertiser and who is worker
    # You can customize this logic based on your task system
    room, created = ChatRoom.objects.get_or_create(
        advertiser=request.user,
        worker=other_user
    )
    
    return redirect('chat:room', room_id=room.id)


@login_required
def get_unread_count(request):
    '''API endpoint to get unread message count'''
    count = Message.objects.filter(
        Q(chat_room__advertiser=request.user) | Q(chat_room__worker=request.user),
        is_read=False
    ).exclude(sender=request.user).count()
    
    return JsonResponse({'unread_count': count})