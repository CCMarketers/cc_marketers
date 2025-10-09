# payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [

    # Funding (inflow)
    path('fund/initiate/', views.initiate_funding, name='initiate_funding'),
    path('fund/callback/', views.payment_callback, name='payment_callback'),

    # Withdrawals (outflow)
    path('withdraw/', views.withdraw_funds, name='withdraw_funds'),

    # Bank utilities
    path('banks/', views.get_banks, name='get_banks'),
    path('verify-account/', views.verify_account, name='verify_account'),

    # Webhooks
    # path('webhooks/paystack/', views.paystack_webhook, name='paystack_webhook'),
    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
    path('webhooks/flutterwave/', views.flutterwave_webhook, name='flutterwave_webhook'),
    path('callback/flutterwave/', views.flutterwave_callback, name='flutterwave_callback'),

    # Monnify
    path('monnify/callback/', views.monnify_callback, name='monnify_callback'),
    path('webhooks/monnify/', views.monnify_webhook, name='monnify_webhook'),
    path('monnify/banks/', views.get_monnify_banks, name='get_monnify_banks'),
    path('monnify/verify-account/', views.verify_monnify_account, name='verify_monnify_account'),

    # Transaction management
    path('transactions/', views.transaction_history, name='transaction_history'),
    path('transactions/<uuid:transaction_id>/', views.transaction_detail, name='transaction_detail'),
]
