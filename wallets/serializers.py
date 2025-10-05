# wallets/serializers.py - DRF Serializers
from rest_framework import serializers
from .models import Wallet, Transaction, WithdrawalRequest

class WalletSerializer(serializers.ModelSerializer):
    available_balance = serializers.SerializerMethodField()
    
    class Meta:
        model = Wallet
        fields = ['balance', 'available_balance', 'created_at', 'updated_at']
        read_only_fields = ['balance', 'created_at', 'updated_at']
    
    def get_available_balance(self, obj):
        return obj.get_available_balance()

class TransactionSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_type', 'category', 'category_display',
            'amount', 'balance_after', 'status', 'status_display',
            'reference', 'description', 'created_at'
        ]
        read_only_fields = '__all__'

class WithdrawalRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'amount', 'withdrawal_method', 'account_number',
            'account_name', 'bank_name', 'status', 'status_display',
            'created_at', 'processed_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'processed_at']

