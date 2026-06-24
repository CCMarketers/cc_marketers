from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_center, name="center"),
    path("api/list/", views.notification_list_api, name="list_api"),
    # int PK — model uses default AutoField, not UUID
    path("api/mark-read/<int:notification_id>/", views.mark_notification_read, name="mark_read"),
    path("api/mark-all-read/", views.mark_all_read, name="mark_all_read"),
    path("api/delete/<int:notification_id>/", views.delete_notification, name="delete"),
]