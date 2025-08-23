
# tasks/admin.py
from django.contrib import admin
from .models import Task, Submission, Dispute

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'advertiser', 'payout_per_slot', 'remaining_slots', 'total_slots', 'deadline', 'status']
    list_filter = ['status', 'created_at', 'deadline']
    search_fields = ['title', 'description', 'advertiser__username']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ['task', 'member', 'status', 'submitted_at', 'reviewed_by']
    list_filter = ['status', 'submitted_at', 'reviewed_at']
    search_fields = ['task__title', 'member__username']
    readonly_fields = ['submitted_at', 'reviewed_at']

@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ['id', 'submission', 'raised_by', 'status', 'created_at', 'resolved_by']
    list_filter = ['status', 'created_at', 'resolved_at']
    search_fields = ['submission__task__title', 'raised_by__username']
    readonly_fields = ['created_at', 'resolved_at']
