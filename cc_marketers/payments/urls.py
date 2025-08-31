# payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Payment initiation and callbacks
    path('fund/initiate/', views.initiate_funding, name='initiate_funding'),
    path('callback/', views.payment_callback, name='payment_callback'),
    
    # Withdrawals
    path('withdraw/', views.withdraw_funds, name='withdraw'),
    
    # API endpoints
    path('api/banks/', views.get_banks, name='get_banks'),
    path('api/verify-account/', views.verify_account, name='verify_account'),
    
    # Webhooks
    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
    
    # Transaction management
    path('transactions/', views.transaction_history, name='transaction_history'),
    path('transactions/<uuid:transaction_id>/', views.transaction_detail, name='transaction_detail'),
]