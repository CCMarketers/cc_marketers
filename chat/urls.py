from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_room_list, name='room_list'),
    path('room/<int:room_id>/', views.chat_room, name='room'),
    path('create/<int:user_id>/', views.get_or_create_room, name='create_room'),
    path('api/unread-count/', views.get_unread_count, name='unread_count'),
]