# wallets/urls.py
from django.urls import path
from . import views

app_name = 'wallets'

urlpatterns = [
    # User wallet views
    path('', views.WalletDashboardView.as_view(), name='dashboard'),
    path('transactions/', views.TransactionListView.as_view(), name='transactions'),
     path("wallets/transactions/<uuid:transaction_id>/", views.wallet_transaction_detail, name="transaction_detail"),

    path('withdraw/', views.WithdrawalRequestView.as_view(), name='withdrawal_request'),
    path('withdrawals/', views.WithdrawalListView.as_view(), name='withdrawal_list'),
    path('fund/', views.FundWalletView.as_view(), name='fund_wallet'),
    
    # Admin wallet views
    path('admin/withdrawals/', views.AdminWithdrawalListView.as_view(), name='admin_withdrawal_list'),
    path('admin/withdrawals/<uuid:pk>/', views.AdminWithdrawalDetailView.as_view(), name='admin_withdrawal_detail'),
    path('admin/escrows/', views.AdminEscrowListView.as_view(), name='admin_escrow_list'),
    path('admin/transactions/', views.AdminTransactionListView.as_view(), name='admin_transaction_list'),
]