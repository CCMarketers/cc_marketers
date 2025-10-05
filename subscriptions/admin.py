
# subscriptions/admin.py
from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'duration_days', 'daily_ad_limit', 'is_active']
    list_filter = ['is_active', 'duration_days']
    search_fields = ['name']
    ordering = ['price']

@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['user', 'plan', 'status', 'start_date', 'expiry_date', 'auto_renewal']
    list_filter = ['status', 'auto_renewal', 'plan']
    search_fields = ['user__username', 'plan__name']
    ordering = ['-created_at']
    readonly_fields = ['start_date', 'created_at']

