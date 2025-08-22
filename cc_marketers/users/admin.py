
# apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from .models import User, UserProfile, EmailVerificationToken, PhoneVerificationToken

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'get_full_name', 'role', 'is_active', 'email_verified', 'phone_verified', 'date_joined')
    list_filter = ('role', 'is_active', 'email_verified', 'phone_verified', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name', 'phone', 'referral_code')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {
            'fields': ('first_name', 'last_name', 'phone', 'bio', 'avatar', 'birth_date')
        }),
        ('Location', {
            'fields': ('country', 'state', 'city')
        }),
        ('Role & Permissions', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Verification', {
            'fields': ('email_verified', 'phone_verified')
        }),
        ('Referral System', {
            'fields': ('referral_code', 'referred_by', 'referral_link')
        }),
        ('Preferences', {
            'fields': ('receive_email_notifications', 'receive_sms_notifications')
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined')
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role'),
        }),
    )
    
    readonly_fields = ('date_joined', 'last_login', 'referral_link')
    
    def referral_link(self, obj):
        if obj.referral_code:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                obj.referral_url,
                obj.referral_url
            )
        return '-'
    referral_link.short_description = 'Referral Link'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'occupation', 'tasks_completed', 'tasks_posted', 'success_rate', 'average_rating')
    list_filter = ('experience_years', 'created_at')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'occupation', 'company')
    readonly_fields = ('tasks_completed', 'tasks_posted', 'success_rate', 'average_rating', 'total_reviews')

@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at', 'used')
    list_filter = ('used', 'created_at', 'expires_at')
    search_fields = ('user__email', 'token')
    readonly_fields = ('token',)

@admin.register(PhoneVerificationToken)
class PhoneVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'token', 'created_at', 'expires_at', 'used')
    list_filter = ('used', 'created_at', 'expires_at')
    search_fields = ('user__phone', 'token')
    readonly_fields = ('token',)