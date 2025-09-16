# wallets/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Sum
from .models import Wallet, Transaction, EscrowTransaction, WithdrawalRequest
\
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'available_balance_display', 'total_earned', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    
    def available_balance_display(self, obj):
        available = obj.get_available_balance() or 0
        color = 'green' if available > 0 else 'red'
        # Format to 2 decimal places before passing to format_html
        formatted = f"{available:.2f}"
        return format_html(
            '<span style="color: {}; font-weight: bold;">${}</span>',
            color,
            formatted
        )
    available_balance_display.short_description = 'Available Balance'

    
    def total_earned(self, obj):
        total = Transaction.objects.filter(
            user=obj.user,
            transaction_type='credit',
            category__in=['task_earning', 'referral_bonus'],
            status='success'
        ).aggregate(total=Sum('amount'))['total'] or 0
        return f'${total:.2f}'
    total_earned.short_description = 'Total Earned'

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'reference_short', 'user', 'transaction_type', 'category', 
        'amount_display', 'status', 'task_link', 'created_at'
    ]
    list_filter = ['transaction_type', 'category', 'status', 'created_at']
    search_fields = ['user__username', 'reference', 'description']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'
    
    def reference_short(self, obj):
        if not obj.reference:  # handle None or empty string
            return "-"
        return obj.reference[:14] + "..." if len(obj.reference) > 14 else obj.reference

    reference_short.short_description = 'Reference'
    
    def amount_display(self, obj):
        color = 'green' if obj.transaction_type == 'credit' else 'red'
        symbol = '+' if obj.transaction_type == 'credit' else '-'
        formatted = f"{obj.amount:.2f}"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} ${}</span>',
            color,
            symbol,
            formatted
        )
    amount_display.short_description = 'Amount'
    
    def task_link(self, obj):
        if getattr(obj, "task_id", None):  # safer than obj.task
            url = reverse('admin:tasks_task_change', args=[obj.task.id])
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.task.title)
        return '-'
    task_link.short_description = 'Related Task'

@admin.register(EscrowTransaction)
class EscrowTransactionAdmin(admin.ModelAdmin):
    list_display = ['task_link', 'advertiser', 'amount', 'status', 'created_at', 'released_at']
    list_filter = ['status', 'created_at']
    search_fields = ['task__title', 'advertiser__username']
    readonly_fields = ['created_at']
    
    def task_link(self, obj):
        if getattr(obj, "task_id", None):
            url = reverse("admin:tasks_task_change", args=[obj.task.id])
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.task.title)
        return "-"


    task_link.short_description = 'Task'

@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id_short', 'user', 'amount', 'withdrawal_method', 
        'status_display', 'created_at', 'processed_by'
    ]
    list_filter = ['status', 'withdrawal_method', 'created_at']
    search_fields = ['user__username', 'account_name', 'bank_name']
    readonly_fields = ['id', 'created_at', 'gateway_response']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Request Details', {
            'fields': ('user', 'amount', 'withdrawal_method', 'status')
        }),
        ('Bank Details', {
            'fields': ('account_number', 'account_name', 'bank_name', 'bank_code')
        }),
        ('Processing', {
            'fields': ('processed_by', 'processed_at', 'admin_notes')
        }),
        ('Gateway Details', {
            'fields': ('gateway_reference', 'gateway_response'),
            'classes': ('collapse',)
        }),
        ('System', {
            'fields': ('id', 'created_at', 'transaction'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['approve_selected', 'reject_selected']
    
    def id_short(self, obj):
        return str(obj.id)[:8] + '...'
    id_short.short_description = 'ID'
    
    def status_display(self, obj):
        colors = {
            'pending': '#f59e0b',
            'approved': '#10b981', 
            'rejected': '#ef4444',
            'completed': '#3b82f6',
            'failed': '#6b7280'
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def approve_selected(self, request, queryset):
        """Bulk approve withdrawal requests"""
        from .services import WalletService
        
        approved_count = 0
        for withdrawal in queryset.filter(status='pending'):
            try:
                WalletService.approve_withdrawal(withdrawal.id, request.user)
                approved_count += 1
            except ValueError:
                pass
        
        self.message_user(request, f'{approved_count} withdrawal requests approved.')
    approve_selected.short_description = 'Approve selected requests'
    
    def reject_selected(self, request, queryset):
        """Bulk reject withdrawal requests"""
        from .services import WalletService
        
        rejected_count = 0
        for withdrawal in queryset.filter(status='pending'):
            try:
                WalletService.reject_withdrawal(withdrawal.id, request.user, "Bulk rejection")
                rejected_count += 1
            except ValueError:
                pass
        
        self.message_user(request, f'{rejected_count} withdrawal requests rejected.')
    reject_selected.short_description = 'Reject selected requests'


# Custom admin site title and header
admin.site.site_title = "Wallet System Admin"
admin.site.site_header = "Wallet System Administration"
admin.site.index_title = "Welcome to Wallet System Admin"