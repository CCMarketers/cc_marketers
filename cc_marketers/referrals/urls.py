# apps/referrals/urls.py
from django.urls import path
from . import views

app_name = 'referrals'

urlpatterns = [
    # User views
    path('', views.ReferralDashboardView.as_view(), name='dashboard'),
    path('my-referrals/', views.ReferralListView.as_view(), name='referral_list'),
    path('earnings/', views.EarningsListView.as_view(), name='earnings_list'),
    path('commission-tiers/', views.CommissionTiersView.as_view(), name='commission_tiers'),
    
    # Admin views
    path('admin/dashboard/', views.AdminReferralDashboardView.as_view(), name='admin_dashboard'),
    path('admin/earnings/', views.AdminEarningsManagementView.as_view(), name='admin_earnings'),
]