from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_center(request):
    qs = Notification.objects.filter(recipient=request.user)
    unread_count = qs.filter(is_read=False).count()
    notifications = qs[:100]
    return render(request, "notifications/center.html", {
        "notifications": notifications,
        "unread_count": unread_count,
    })


@login_required
def notification_list_api(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by("-created_at")[:20]

    unread_count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()

    return JsonResponse({
        "notifications": [n.to_dict() for n in notifications],
        "unread_count": unread_count,
    })


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    updated = Notification.objects.filter(
        id=notification_id, recipient=request.user
    ).update(is_read=True)
    return JsonResponse({"success": bool(updated)})


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)
    return JsonResponse({"success": True})


@login_required
@require_POST
def delete_notification(request, notification_id):
    deleted, _ = Notification.objects.filter(
        id=notification_id, recipient=request.user
    ).delete()
    return JsonResponse({"success": bool(deleted)})