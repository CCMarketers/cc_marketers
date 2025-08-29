# wallets/api.py - Optional REST API endpoints
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from .models import Wallet, Transaction, WithdrawalRequest
from .services import WalletService
from .serializers import WalletSerializer, TransactionSerializer, WithdrawalRequestSerializer

class WalletViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for wallet operations"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        return WalletSerializer
    
    @action(detail=False, methods=['get'])
    def balance(self, request):
        """Get wallet balance and stats"""
        wallet = WalletService.get_or_create_wallet(request.user)
        
        data = {
            'balance': wallet.balance,
            'available_balance': wallet.get_available_balance(),
            'total_earned': Transaction.objects.filter(
                user=request.user,
                transaction_type='credit',
                category__in=['task_earning', 'referral_bonus'],
                status='success'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'total_withdrawn': Transaction.objects.filter(
                user=request.user,
                transaction_type='debit', 
                category='withdrawal',
                status='success'
            ).aggregate(total=Sum('amount'))['total'] or 0
        }
        
        return Response(data)
    
    @action(detail=False, methods=['post'])
    def withdraw(self, request):
        """Create withdrawal request via API"""
        try:
            withdrawal = WalletService.create_withdrawal_request(
                user=request.user,
                amount=request.data.get('amount'),
                withdrawal_method=request.data.get('withdrawal_method', 'paystack'),
                account_details=request.data.get('account_details', {})
            )
            
            serializer = WithdrawalRequestSerializer(withdrawal)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
