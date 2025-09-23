# payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # # Payment initiation and callbacks
    # path('fund/initiate/', views.initiate_funding, name='initiate_funding'),
    # path('callback/', views.payment_callback, name='payment_callback'),
    
    # # Withdrawals
    # path('withdraw/', views.withdraw_funds, name='withdraw'),
    
    # # API endpoints
    # path('api/banks/', views.get_banks, name='get_banks'),
    # path('api/verify-account/', views.verify_account, name='verify_account'),
    
    # # Webhooks
    # path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
    
    # # Transaction management
    # path('transactions/', views.transaction_history, name='transaction_history'),
    # path('transactions/<uuid:transaction_id>/', views.transaction_detail, name='transaction_detail'),
    #     # Existing URLs...
    # path('fund/', views.initiate_funding, name='initiate_funding'),
    # path('fund/flutterwave/', views.initiate_flutterwave_funding, name='initiate_flutterwave_funding'),
    # path('callback/', views.payment_callback, name='payment_callback'),
    # path('callback/flutterwave/', views.flutterwave_callback, name='flutterwave_callback'),
    # path('withdraw/', views.withdraw_funds, name='withdraw_funds'),
    # path('withdraw/flutterwave/', views.withdraw_funds_flutterwave, name='withdraw_funds_flutterwave'),
    # path('banks/', views.get_banks, name='get_banks'),
    # path('banks/flutterwave/', views.get_flutterwave_banks, name='get_flutterwave_banks'),
    # path('verify-account/', views.verify_account, name='verify_account'),
    # path('verify-account/flutterwave/', views.verify_flutterwave_account, name='verify_flutterwave_account'),
    # path('webhooks/paystack/', views.paystack_webhook, name='paystack_webhook'),
    # path('webhooks/flutterwave/', views.flutterwave_webhook, name='flutterwave_webhook'),
    # path('transactions/', views.transaction_history, name='transaction_history'),
    # path('transactions/<uuid:transaction_id>/', views.transaction_detail, name='transaction_detail'),

    # Funding (inflow)
    path('fund/initiate/', views.initiate_funding, name='initiate_funding'),
    path('fund/callback/', views.payment_callback, name='payment_callback'),

    # Withdrawals (outflow)
    path('withdraw/', views.withdraw_funds, name='withdraw_funds'),

    # Bank utilities
    path('banks/', views.get_banks, name='get_banks'),
    path('verify-account/', views.verify_account, name='verify_account'),

    # Webhooks
    path('webhooks/paystack/', views.paystack_webhook, name='paystack_webhook'),
    path('webhooks/flutterwave/', views.flutterwave_webhook, name='flutterwave_webhook'),
    path('callback/flutterwave/', views.flutterwave_callback, name='flutterwave_callback'),

    # Transaction management
    path('transactions/', views.transaction_history, name='transaction_history'),
    path('transactions/<uuid:transaction_id>/', views.transaction_detail, name='transaction_detail'),
]
