
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
    
    # Review URLs
    path('<int:task_id>/review/', views.review_submissions, name='review_submissions'),
    path('submission/<int:submission_id>/review/', views.review_submission, name='review_submission'),
    
    # Dispute URLs
    path('submission/<int:submission_id>/dispute/', views.create_dispute, name='create_dispute'),
    path('my-disputes/', views.my_disputes, name='my_disputes'),
    path('dispute/<int:dispute_id>/', views.dispute_detail, name='dispute_detail'),
    
    # Admin URLs
    path('admin/disputes/', views.admin_disputes, name='admin_disputes'),
    path('admin/dispute/<int:dispute_id>/resolve/', views.resolve_dispute, name='resolve_dispute'),
]
