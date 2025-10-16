# apps/referrals/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum
from .models import ReferralCode, Referral, ReferralEarning, CommissionTier
from django.urls import reverse

@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ['user', 'code', 'is_active', 'created_at', 'referral_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__username', 'user__email', 'code']
    readonly_fields = ['code', 'created_at']
    
    def referral_count(self, obj):
        return obj.referral_set.count()
    referral_count.short_description = 'Total Referrals'

@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'referred', 'level', 'is_active', 'created_at', 'total_earnings']
    list_filter = ['level', 'is_active', 'created_at']
    search_fields = ['referrer__username', 'referred__username', 'referrer__email', 'referred__email']
    readonly_fields = ['created_at']
    raw_id_fields = ['referrer', 'referred', 'referral_code']
    
    def total_earnings(self, obj):
        total = obj.referralearning_set.filter(
            status__in=['approved', 'paid']
        ).aggregate(total=Sum('amount'))['total'] or 0
        return f'₦{total:.2f}'
    total_earnings.short_description = 'Total Earnings'



@admin.register(ReferralEarning)
class ReferralEarningAdmin(admin.ModelAdmin):
    list_display = [
        'referrer',
        'referred_user',
        'amount_display',
        'earning_type',
        'commission_rate',
        'status_display',
        'level_display',
        'transaction_link',
        'created_at',
    ]
    list_filter = ['status', 'earning_type', 'created_at', 'referral__level']
    search_fields = [
        'referrer__username',
        'referred_user__username',
        'transaction_id',
    ]
    readonly_fields = ['created_at', 'approved_at', 'paid_at']
    raw_id_fields = ['referrer', 'referred_user', 'referral']
    actions = ['approve_earnings', 'mark_as_paid', 'cancel_earnings']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'referrer',
                'referred_user',
                'referral',
                'amount',
                'earning_type',
            )
        }),
        ('Commission Details', {
            'fields': ('commission_rate', 'status')
        }),
        ('Transaction Details', {
            'fields': ('transaction_id', 'transaction_link')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'approved_at', 'paid_at'),
            'classes': ('collapse',)
        }),
    )

    # ====== Custom Display Methods ======
    def amount_display(self, obj):
        return f'₦{obj.amount:.2f}'
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'

    def status_display(self, obj):
        colors = {
            'pending': 'orange',
            'approved': 'blue',
            'paid': 'green',
            'cancelled': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'

    def level_display(self, obj):
        return f'Level {obj.referral.level}'
    level_display.short_description = 'Referral Level'
    level_display.admin_order_field = 'referral__level'

    def transaction_link(self, obj):
        """Link to related wallet transaction if exists"""
        if obj.transaction_id:
            url = reverse('admin:wallets_transaction_changelist') + f'?q={obj.transaction_id}'
            return format_html('<a href="{}" target="_blank">View Transaction</a>', url)
        return '-'
    transaction_link.short_description = 'Transaction'

    # ====== Admin Actions ======
    def approve_earnings(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='pending').update(
            status='approved', approved_at=timezone.now()
        )
        self.message_user(request, f'{updated} earnings approved successfully.')
    approve_earnings.short_description = 'Approve selected earnings'

    def mark_as_paid(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='approved').update(
            status='paid', paid_at=timezone.now()
        )
        self.message_user(request, f'{updated} earnings marked as paid.')
    mark_as_paid.short_description = 'Mark selected earnings as paid'

    def cancel_earnings(self, request, queryset):
        updated = queryset.filter(status__in=['pending', 'approved']).update(status='cancelled')
        self.message_user(request, f'{updated} earnings cancelled.')
    cancel_earnings.short_description = 'Cancel selected earnings'


@admin.register(CommissionTier)
class CommissionTierAdmin(admin.ModelAdmin):
    list_display = ['level', 'earning_type', 'rate_display', 'is_active', 'created_at']
    list_filter = ['level', 'earning_type', 'is_active', 'created_at']
    search_fields = ['earning_type']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Commission Setup', {
            'fields': ('level', 'earning_type', 'rate', 'is_active')
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def rate_display(self, obj):
        return f'{obj.rate}%'
    rate_display.short_description = 'Commission Rate'
    rate_display.admin_order_field = 'rate'

# Custom admin site configuration
admin.site.site_header = 'Referral System Administration'
admin.site.site_title = 'Referral Admin'
admin.site.index_title = 'Welcome to Referral System Administration'