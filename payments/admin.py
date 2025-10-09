# payments/admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import PaymentGateway, PaymentTransaction, PaystackTransaction, WebhookEvent, FlutterwaveTransaction, MonnifyTransaction

 
@admin.register(PaymentGateway)
class PaymentGatewayAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at']


class PaystackTransactionInline(admin.StackedInline):
    model = PaystackTransaction
    readonly_fields = ['authorization_url', 'access_code', 'paystack_reference', 
                      'recipient_code', 'transfer_code', 'created_at']
    extra = 0


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ['internal_reference', 'user', 'transaction_type', 'amount_usd', 
                   'currency', 'status', 'gateway', 'created_at']
    list_filter = ['transaction_type', 'status', 'gateway', 'currency', 'created_at']
    search_fields = ['user__username', 'user__email', 'gateway_reference', 'internal_reference']
    readonly_fields = ['id', 'internal_reference', 'created_at', 'updated_at', 'completed_at']
    date_hierarchy = 'created_at'
    inlines = [PaystackTransactionInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'gateway')
    
    def colored_status(self, obj):
        colors = {
            'pending': '#fbbf24',
            'success': '#10b981',
            'failed': '#ef4444',
            'cancelled': '#6b7280'
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    colored_status.short_description = 'Status'


@admin.register(PaystackTransaction)
class PaystackTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'paystack_reference', 'recipient_code', 'created_at']
    list_filter = ['created_at']
    search_fields = ['paystack_reference', 'transaction__gateway_reference', 
                    'transaction__user__username']
    readonly_fields = ['created_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('transaction__user')


class PaystackTransactionInline(admin.StackedInline):
    model = PaystackTransaction
    extra = 0


class FlutterwaveTransactionInline(admin.StackedInline):
    model = FlutterwaveTransaction
    extra = 0


@admin.register(FlutterwaveTransaction)
class FlutterwaveTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction', 'flutterwave_reference', 'flutterwave_id', 
        'payment_link', 'transfer_id', 'created_at'
    ]
    search_fields = ['flutterwave_reference', 'flutterwave_id', 'transfer_id']
    readonly_fields = ['created_at']


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'gateway', 'event_type', 'reference', 'processed', 
        'created_at', 'processed_at'
    ]
    list_filter = ['gateway', 'event_type', 'processed', 'created_at']
    search_fields = ['reference']
    readonly_fields = ['id', 'created_at', 'processed_at']
    date_hierarchy = 'created_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('gateway')



@admin.register(MonnifyTransaction)
class MonnifyTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'transaction_reference', 'account_number', 'bank_name', 'created_at']
    search_fields = ['transaction_reference', 'account_number', 'account_name']
    list_filter = ['bank_name', 'created_at']
    readonly_fields = ['created_at']