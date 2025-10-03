# =======================
# USER APP - MODELS
# =======================

# users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    CURRENCY_CHOICES = [
        ('NGN', 'NGN'),
        ('GHS', 'GHS'),
        ('KES', 'KES'),
        ('USD', 'KES'),
    ]
    
    COUNTRY_CHOICES = [
        ('NG', 'Nigeria'),
        ('GH', 'Ghana'),
        ('KE', 'Kenya'),
        ('US', 'United States'),
    ]
    
    preferred_currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='NGN'
    )
    country = models.CharField(
        max_length=2,
        choices=COUNTRY_CHOICES,
        null=True,
        blank=True
    )
    phone = models.CharField(max_length=20, blank=True)
    
    def __str__(self):
        return f"{self.username} ({self.preferred_currency})"


# =======================
# WALLETS APP - MODELS
# =======================

# wallets/models.py
from django.db import models
from django.conf import settings
from decimal import Decimal

class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance_usd = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00')
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} - ${self.balance_usd}"
    
    def can_withdraw(self, amount_usd):
        return self.balance_usd >= amount_usd

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('funding', 'Funding'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount_usd = models.DecimalField(max_digits=15, decimal_places=2)
    amount_local = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Payment gateway fields
    gateway_reference = models.CharField(max_length=255, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Metadata
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transaction_type} - ${self.amount_usd} ({self.currency})"


# =======================
# PAYMENTS APP - MODELS
# =======================

# payments/models.py
from django.db import models

class CurrencyRate(models.Model):
    base_currency = models.CharField(max_length=3, default='USD')
    target_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=10, decimal_places=4)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['base_currency', 'target_currency']
    
    def __str__(self):
        return f"{self.base_currency} → {self.target_currency}: {self.rate}"


# =======================
# PAYMENTS APP - SERVICES
# =======================

# payments/services.py
import requests
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
from .models import CurrencyRate

class CurrencyService:
    """Handles currency conversion and rate management"""
    
    @classmethod
    def get_exchange_rate(cls, from_currency='USD', to_currency='NGN'):
        """Get exchange rate with caching"""
        cache_key = f"rate_{from_currency}_{to_currency}"
        rate = cache.get(cache_key)
        
        if rate is None:
            # Try to get from database first
            try:
                currency_rate = CurrencyRate.objects.get(
                    base_currency=from_currency,
                    target_currency=to_currency
                )
                rate = currency_rate.rate
            except CurrencyRate.DoesNotExist:
                # Fetch from external API (example with exchangerate-api)
                rate = cls._fetch_rate_from_api(from_currency, to_currency)
            
            # Cache for 1 hour
            cache.set(cache_key, rate, 3600)
        
        return Decimal(str(rate))
    
    @classmethod
    def _fetch_rate_from_api(cls, from_currency, to_currency):
        """Fetch rate from external API"""
        try:
            # Example using exchangerate-api (replace with your preferred service)
            url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
            response = requests.get(url, timeout=10)
            data = response.json()
            
            rate = data['rates'].get(to_currency, 1)
            
            # Update/create in database
            CurrencyRate.objects.update_or_create(
                base_currency=from_currency,
                target_currency=to_currency,
                defaults={'rate': Decimal(str(rate))}
            )
            
            return rate
        except:
            # Fallback rates (you should have more robust error handling)
            fallback_rates = {
                'NGN': 1600,  # 1 USD = 1600 NGN
                'GHS': 15.5,  # 1 USD = 15.5 GHS
                'KES': 155,   # 1 USD = 155 KES
            }
            return fallback_rates.get(to_currency, 1)
    
    @classmethod
    def convert_usd_to_local(cls, amount_usd, target_currency):
        """Convert USD to local currency"""
        if target_currency == 'USD':
            return amount_usd
        
        rate = cls.get_exchange_rate('USD', target_currency)
        return amount_usd * rate
    
    @classmethod
    def convert_local_to_usd(cls, amount_local, from_currency):
        """Convert local currency to USD"""
        if from_currency == 'USD':
            return amount_local
        
        rate = cls.get_exchange_rate('USD', from_currency)
        return amount_local / rate


class PaymentGatewayService:
    """Handles payment gateway integrations"""
    
    @classmethod
    def initialize_payment(cls, amount_local, currency, email, reference):
        """Initialize payment with appropriate gateway"""
        if currency == 'NGN':
            return cls._paystack_initialize(amount_local, currency, email, reference)
        elif currency in ['GHS', 'KES']:
            return cls._flutterwave_initialize(amount_local, currency, email, reference)
        else:
            raise ValueError(f"Unsupported currency: {currency}")
    
    @classmethod
    def _paystack_initialize(cls, amount_kobo, currency, email, reference):
        """Initialize Paystack payment"""
        url = "https://api.paystack.co/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        # Convert to kobo for Paystack
        amount_kobo = int(amount_kobo * 100)
        
        data = {
            "email": email,
            "amount": amount_kobo,
            "currency": currency,
            "reference": reference,
            "callback_url": f"{settings.FRONTEND_URL}/payment/callback"
        }
        
        response = requests.post(url, json=data, headers=headers)
        return response.json()
    
    @classmethod
    def _flutterwave_initialize(cls, amount, currency, email, reference):
        """Initialize Flutterwave payment"""
        url = "https://api.flutterwave.com/v3/payments"
        headers = {
            "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "tx_ref": reference,
            "amount": str(amount),
            "currency": currency,
            "customer": {
                "email": email,
            },
            "redirect_url": f"{settings.FRONTEND_URL}/payment/callback",
            "payment_options": "card,banktransfer,ussd"
        }
        
        response = requests.post(url, json=data, headers=headers)
        return response.json()
    
    @classmethod
    def verify_payment(cls, reference, currency):
        """Verify payment status"""
        if currency == 'NGN':
            return cls._paystack_verify(reference)
        else:
            return cls._flutterwave_verify(reference)
    
    @classmethod
    def _paystack_verify(cls, reference):
        """Verify Paystack payment"""
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        }
        
        response = requests.get(url, headers=headers)
        return response.json()
    
    @classmethod
    def _flutterwave_verify(cls, reference):
        """Verify Flutterwave payment"""
        url = f"https://api.flutterwave.com/v3/transactions/verify_by_reference?tx_ref={reference}"
        headers = {
            "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
        }
        
        response = requests.get(url, headers=headers)
        return response.json()


# =======================
# WALLETS APP - VIEWS
# =======================

# wallets/views.py
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from payments.services import CurrencyService
from .models import Wallet, Transaction
import uuid

class WalletDashboardView(LoginRequiredMixin, TemplateView):
    """Wallet dashboard showing balance and recent transactions"""
    template_name = 'wallets/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet, created = Wallet.objects.get_or_create(user=self.request.user)
        
        # Get balance in USD and local currency
        user_currency = self.request.user.preferred_currency
        balance_local = CurrencyService.convert_usd_to_local(
            wallet.balance_usd, 
            user_currency
        )
        
        context.update({
            'wallet': wallet,
            'balance_local': balance_local,
            'user_currency': user_currency,
            'recent_transactions': wallet.transactions.all()[:10]
        })
        return context


class WalletBalanceAPIView(LoginRequiredMixin, APIView):
    """API endpoint to get wallet balance"""
    
    def get(self, request):
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        user_currency = request.user.preferred_currency
        
        balance_local = CurrencyService.convert_usd_to_local(
            wallet.balance_usd,
            user_currency
        )
        
        return Response({
            'balance_usd': wallet.balance_usd,
            'balance_local': balance_local,
            'currency': user_currency,
        })


# =======================
# PAYMENTS APP - VIEWS
# =======================

# payments/views.py
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from wallets.models import Wallet, Transaction
from .services import CurrencyService, PaymentGatewayService
import uuid
import json
from decimal import Decimal

class InitiateFundingView(LoginRequiredMixin, APIView):
    """Initiate wallet funding"""
    
    def post(self, request):
        try:
            data = request.data
            amount_usd = Decimal(str(data.get('amount_usd', 0)))
            
            if amount_usd <= 0:
                return Response(
                    {'error': 'Amount must be greater than 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get or create wallet
            wallet, created = Wallet.objects.get_or_create(user=request.user)
            
            # Convert to user's local currency
            user_currency = request.user.preferred_currency
            amount_local = CurrencyService.convert_usd_to_local(
                amount_usd, 
                user_currency
            )
            
            # Generate unique reference
            reference = f"fund_{request.user.id}_{uuid.uuid4().hex[:8]}"
            
            # Create pending transaction
            transaction = Transaction.objects.create(
                wallet=wallet,
                transaction_type='funding',
                amount_usd=amount_usd,
                amount_local=amount_local,
                currency=user_currency,
                gateway_reference=reference,
                description=f"Wallet funding: ${amount_usd}",
                status='pending'
            )
            
            # Initialize payment with gateway
            gateway_response = PaymentGatewayService.initialize_payment(
                amount_local=amount_local,
                currency=user_currency,
                email=request.user.email,
                reference=reference
            )
            
            # Update transaction with gateway response
            transaction.gateway_response = gateway_response
            transaction.save()
            
            if gateway_response.get('status'):
                return Response({
                    'success': True,
                    'transaction_id': transaction.id,
                    'payment_url': gateway_response.get('data', {}).get('authorization_url') or 
                                   gateway_response.get('data', {}).get('link'),
                    'reference': reference,
                    'amount_usd': amount_usd,
                    'amount_local': amount_local,
                    'currency': user_currency
                })
            else:
                transaction.status = 'failed'
                transaction.save()
                return Response(
                    {'error': 'Failed to initialize payment'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class InitiateWithdrawalView(LoginRequiredMixin, APIView):
    """Initiate wallet withdrawal"""
    
    def post(self, request):
        try:
            data = request.data
            amount_usd = Decimal(str(data.get('amount_usd', 0)))
            bank_details = data.get('bank_details', {})
            
            if amount_usd <= 0:
                return Response(
                    {'error': 'Amount must be greater than 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get wallet
            wallet = get_object_or_404(Wallet, user=request.user)
            
            # Check if user has sufficient balance
            if not wallet.can_withdraw(amount_usd):
                return Response(
                    {'error': 'Insufficient balance'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Convert to local currency
            user_currency = request.user.preferred_currency
            amount_local = CurrencyService.convert_usd_to_local(
                amount_usd,
                user_currency
            )
            
            # Generate reference
            reference = f"withdraw_{request.user.id}_{uuid.uuid4().hex[:8]}"
            
            # Create transaction
            transaction = Transaction.objects.create(
                wallet=wallet,
                transaction_type='withdrawal',
                amount_usd=amount_usd,
                amount_local=amount_local,
                currency=user_currency,
                gateway_reference=reference,
                description=f"Wallet withdrawal: ${amount_usd}",
                status='processing'
            )
            
            # Debit wallet immediately (you might want to do this after successful payout)
            wallet.balance_usd -= amount_usd
            wallet.save()
            
            # Here you would integrate with payout API
            # For now, we'll simulate success
            transaction.status = 'completed'
            transaction.save()
            
            return Response({
                'success': True,
                'transaction_id': transaction.id,
                'reference': reference,
                'amount_usd': amount_usd,
                'amount_local': amount_local,
                'currency': user_currency,
                'message': 'Withdrawal initiated successfully'
            })
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class PaymentWebhookView(View):
    """Handle payment gateway webhooks"""
    
    def post(self, request):
        try:
            # Parse webhook data
            body = json.loads(request.body)
            
            # Determine gateway based on request headers or body structure
            if 'paystack' in request.META.get('HTTP_USER_AGENT', '').lower():
                return self._handle_paystack_webhook(body)
            else:
                return self._handle_flutterwave_webhook(body)
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    def _handle_paystack_webhook(self, data):
        """Handle Paystack webhook"""
        event = data.get('event')
        
        if event == 'charge.success':
            reference = data['data']['reference']
            
            try:
                transaction = Transaction.objects.get(
                    gateway_reference=reference,
                    status='pending'
                )
                
                # Verify payment
                verification = PaymentGatewayService.verify_payment(
                    reference, 
                    transaction.currency
                )
                
                if verification.get('data', {}).get('status') == 'success':
                    # Update transaction
                    transaction.status = 'completed'
                    transaction.gateway_response = verification
                    transaction.save()
                    
                    # Credit wallet
                    transaction.wallet.balance_usd += transaction.amount_usd
                    transaction.wallet.save()
                    
                    return JsonResponse({'status': 'success'})
                
            except Transaction.DoesNotExist:
                pass
        
        return JsonResponse({'status': 'ignored'})
    
    def _handle_flutterwave_webhook(self, data):
        """Handle Flutterwave webhook"""
        event = data.get('event')
        
        if event == 'charge.completed':
            reference = data['data']['tx_ref']
            
            try:
                transaction = Transaction.objects.get(
                    gateway_reference=reference,
                    status='pending'
                )
                
                # Verify payment
                verification = PaymentGatewayService.verify_payment(
                    reference,
                    transaction.currency
                )
                
                if verification.get('data', {}).get('status') == 'successful':
                    # Update transaction
                    transaction.status = 'completed'
                    transaction.gateway_response = verification
                    transaction.save()
                    
                    # Credit wallet
                    transaction.wallet.balance_usd += transaction.amount_usd
                    transaction.wallet.save()
                    
                    return JsonResponse({'status': 'success'})
                    
            except Transaction.DoesNotExist:
                pass
        
        return JsonResponse({'status': 'ignored'})


# =======================
# URLS CONFIGURATION
# =======================

# wallets/urls.py
from django.urls import path
from . import views

app_name = 'wallets'

urlpatterns = [
    path('dashboard/', views.WalletDashboardView.as_view(), name='dashboard'),
    path('api/balance/', views.WalletBalanceAPIView.as_view(), name='api_balance'),
]

# payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('api/fund/', views.InitiateFundingView.as_view(), name='api_fund'),
    path('api/withdraw/', views.InitiateWithdrawalView.as_view(), name='api_withdraw'),
    path('webhook/', views.PaymentWebhookView.as_view(), name='webhook'),
]

# =======================
# SETTINGS ADDITIONS
# =======================

# settings.py additions
"""
# Payment Gateway Settings
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY')
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY')

FLUTTERWAVE_PUBLIC_KEY = os.getenv('FLUTTERWAVE_PUBLIC_KEY')
FLUTTERWAVE_SECRET_KEY = os.getenv('FLUTTERWAVE_SECRET_KEY')

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')

# Cache (for exchange rates)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
"""