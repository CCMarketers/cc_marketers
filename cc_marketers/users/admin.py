from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, UserProfile, EmailVerificationToken, PhoneVerificationToken


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    readonly_fields = ('tasks_completed', 'tasks_posted', 'success_rate', 'average_rating', 'total_reviews')
    fieldsets = (
        ('Profile Info', {
            'fields': ('occupation', 'company', 'location', 'website', 'skills', 'experience_years')
        }),
        ('Social Links', {
            'fields': ('twitter_url', 'linkedin_url', 'facebook_url')
        }),
        ('Stats', {
            'fields': ('tasks_completed', 'tasks_posted', 'success_rate', 'average_rating', 'total_reviews')
        }),
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'get_full_name', 'role', 'is_active', 'email_verified', 'phone_verified', 'date_joined')
    list_filter = ('role', 'is_active', 'email_verified', 'phone_verified', 'date_joined')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone', 'preferred_currency')}),
        ('Role & Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Verification', {'fields': ('email_verified', 'phone_verified')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role'),
        }),
    )

    readonly_fields = ('date_joined', 'last_login')

    inlines = [UserProfileInline]   # Attach profile inline


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'occupation', 'experience_years', 'tasks_completed', 'tasks_posted', 'success_rate', 'average_rating')
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
