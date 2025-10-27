
# tasks/urls.py
from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    # Task URLs
    path('', views.task_list, name='task_list'),
    path('create/', views.create_task, name='create_task'),
    path('my-tasks/', views.my_tasks, name='my_tasks'),
    path('my-submissions/', views.my_submissions, name='my_submissions'),
    path('<int:task_id>/', views.task_detail, name='task_detail'),
    path("task/<int:task_id>/edit/", views.edit_task, name="edit_task"),
    path("task/<int:task_id>/delete/", views.delete_task, name="delete_task"),

    # TimeWall postback endpoint (webhook)
    path('timewall/postback/', views.timewall_postback, name='timewall_postback'),
    path('timewall', views.offerwall_view, name='timewall'),
    path('wallet/balance/', views.task_wallet_balance, name='task_wallet_balance'),

    #Chats 
    # path('task/<int:task_id>/chat/', views.task_chat, name='task_chat'),
    path('chat-with-advertiser/<int:task_id>/', views.chat_with_advertiser, name='chat_with_advertiser'),
    path('chat-with-advertiser/<int:task_id>/', views.chat_with_advertiser, name='chat_with_advertiser'),
    # path('my-chats/', views.my_worker_chats, name='my_worker_chats'),
    
    # Review URLs
    path('<int:task_id>/review/', views.review_submissions, name='review_submissions'),
    path('submission/<int:submission_id>/review/', views.review_submission, name='review_submission'),
    path("resubmit/<int:submission_id>/", views.resubmit_submission, name="resubmit_submission"),

    
    # Task wallet
    path("task-wallet/", views.TaskWalletDashboardView.as_view(), name="task_wallet_dashboard"),
    path("task-wallet/transactions/", views.TaskWalletTransactionListView.as_view(), name="task_wallet_transactions"),
    # path("task-wallet/topup/", views.TaskWalletTopupView.as_view(), name="task_wallet_topup"),

    # Dispute URLs
    path('submission/<int:submission_id>/dispute/', views.create_dispute, name='create_dispute'),
    path('my-disputes/', views.my_disputes, name='my_disputes'),
    path('dispute/<int:dispute_id>/', views.dispute_detail, name='dispute_detail'),
    
    # Admin URLs
    path('admin/disputes/', views.admin_disputes, name='admin_disputes'),
    path('admin/dispute/<int:dispute_id>/resolve/', views.resolve_dispute, name='resolve_dispute'),


    path("transfer-to-task-wallet/", views.transfer_to_task_wallet_view, name="transfer_to_task_wallet"),
    path("transfer-to-main/", views.transfer_to_main_wallet_view, name="transfer_to_main_wallet"),

]
