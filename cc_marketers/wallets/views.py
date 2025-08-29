# wallets/views.py
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView
from django.urls import reverse_lazy
from django.db.models import Q, Sum
from decimal import Decimal
from .models import Wallet, Transaction, WithdrawalRequest, EscrowTransaction
from .services import WalletService
from .forms import WithdrawalRequestForm, FundWalletForm
from subscriptions.decorators import subscription_required, plan_required

# Admin Views
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator

class WalletDashboardView(LoginRequiredMixin, DetailView):
    """Main wallet dashboard showing balance, recent transactions"""
    model = Wallet
    template_name = 'wallets/dashboard.html'
    context_object_name = 'wallet'
    
    def get_object(self):
        return WalletService.get_or_create_wallet(self.request.user)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        wallet = self.object
        
        # Recent transactions (last 10)
        context['recent_transactions'] = Transaction.objects.filter(
            user=user
        )[:10]
        
        # Statistics
        context['total_earned'] = Transaction.objects.filter(
            user=user,
            transaction_type='credit',
            category__in=['task_earning', 'referral_bonus', 'escrow_release', 'task_payment', 'task_completion']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        context['total_withdrawn'] = Transaction.objects.filter(
            user=user,
            transaction_type='debit',
            category='withdrawal',
            status='success'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        pending_withdrawals = WithdrawalRequest.objects.filter(
            user=user,
            status='pending'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        context['pending_withdrawals'] = pending_withdrawals
        
        # Raw wallet balance
        context['wallet_balance'] = wallet.balance
        
        # Available balance (balance - pending withdrawals - escrow)
        context['available_balance'] = wallet.get_available_balance() - pending_withdrawals
        
        return context


@method_decorator(subscription_required, name='dispatch')
class TransactionListView(LoginRequiredMixin, ListView):
    """List all user transactions with filters"""
    model = Transaction
    template_name = 'wallets/transactions.html'
    context_object_name = 'transactions'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = Transaction.objects.filter(user=self.request.user)
        
        # Filter by transaction type
        transaction_type = self.request.GET.get('type')
        if transaction_type in ['credit', 'debit']:
            queryset = queryset.filter(transaction_type=transaction_type)
        
        # Filter by category
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transaction_types'] = Transaction.TRANSACTION_TYPES
        context['transaction_categories'] = Transaction.TRANSACTION_CATEGORIES
        context['transaction_status'] = Transaction.TRANSACTION_STATUS
        return context


@method_decorator(subscription_required, name='dispatch')
@method_decorator(plan_required("Business Member Plan"), name="dispatch")
class WithdrawalRequestView(LoginRequiredMixin, CreateView):
    """Create withdrawal request"""
    model = WithdrawalRequest
    form_class = WithdrawalRequestForm
    template_name = 'wallets/withdrawal_request.html'
    success_url = reverse_lazy('wallets:withdrawal_list')
    
    def form_valid(self, form):
        try:
            account_details = {
                'account_number': form.cleaned_data['account_number'],
                'account_name': form.cleaned_data['account_name'],
                'bank_name': form.cleaned_data['bank_name'],
                'bank_code': form.cleaned_data['bank_code'],
            }
            
            WalletService.create_withdrawal_request(
                user=self.request.user,
                amount=form.cleaned_data['amount'],
                withdrawal_method=form.cleaned_data['withdrawal_method'],
                account_details=account_details
            )
            
            messages.success(self.request, 'Withdrawal request submitted successfully!')
            return redirect(self.success_url)
            
        except ValueError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet = WalletService.get_or_create_wallet(self.request.user)
        context['wallet'] = wallet
        context['available_balance'] = wallet.get_available_balance()
        return context

@method_decorator(subscription_required, name='dispatch')
@method_decorator(plan_required("Business Member Plan"), name="dispatch")
class WithdrawalListView(LoginRequiredMixin, ListView):
    """List user's withdrawal requests"""
    model = WithdrawalRequest
    template_name = 'wallets/withdrawal_list.html'
    context_object_name = 'withdrawals'
    paginate_by = 10
    
    def get_queryset(self):
        return WithdrawalRequest.objects.filter(user=self.request.user)


class FundWalletView(LoginRequiredMixin, CreateView):
    """Fund wallet (for testing/admin purposes)"""
    template_name = 'wallets/fund_wallet.html'
    form_class = FundWalletForm
    success_url = reverse_lazy('wallets:dashboard')
    
    def form_valid(self, form):
        try:
            WalletService.credit_wallet(
                user=self.request.user,
                amount=form.cleaned_data['amount'],
                category='admin_adjustment',
                description=form.cleaned_data.get('description', 'Wallet funding'),
                reference=f"FUND_{self.request.user.id}"
            )
            
            messages.success(self.request, f"Wallet funded with ${form.cleaned_data['amount']}")
            return redirect(self.success_url)
            
        except Exception as e:
            messages.error(self.request, f"Error funding wallet: {str(e)}")
            return self.form_invalid(form)



@method_decorator(staff_member_required, name='dispatch')
class AdminWithdrawalListView(ListView):
    """Admin view to manage withdrawal requests"""
    model = WithdrawalRequest
    template_name = 'wallets/admin/withdrawal_list.html'
    context_object_name = 'withdrawals'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = WithdrawalRequest.objects.all()
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset

@method_decorator(staff_member_required, name='dispatch')
class AdminWithdrawalDetailView(DetailView):
    """Admin view to approve/reject withdrawal requests"""
    model = WithdrawalRequest
    template_name = 'wallets/admin/withdrawal_detail.html'
    context_object_name = 'withdrawal'
    
    def post(self, request, *args, **kwargs):
        withdrawal = self.get_object()
        action = request.POST.get('action')
        
        try:
            if action == 'approve':
                gateway_ref = request.POST.get('gateway_reference', '')
                WalletService.approve_withdrawal(withdrawal.id, request.user, gateway_ref)
                messages.success(request, 'Withdrawal approved successfully!')
                
            elif action == 'reject':
                reason = request.POST.get('reason', '')
                WalletService.reject_withdrawal(withdrawal.id, request.user, reason)
                messages.success(request, 'Withdrawal rejected!')
                
        except ValueError as e:
            messages.error(request, str(e))
        
        return redirect('wallets:admin_withdrawal_detail', pk=withdrawal.id)

@method_decorator(staff_member_required, name='dispatch')
class AdminEscrowListView(ListView):
    """Admin view to monitor escrow transactions"""
    model = EscrowTransaction
    template_name = 'wallets/admin/escrow_list.html'
    context_object_name = 'escrows'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = EscrowTransaction.objects.all().select_related('task', 'advertiser')
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        return queryset


@method_decorator(staff_member_required, name='dispatch')
class AdminTransactionListView(ListView):
    """Admin view to monitor all transactions"""
    model = Transaction
    template_name = 'wallets/admin/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = Transaction.objects.all().select_related('user')
        
        # Search by username
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__username__icontains=search) |
                Q(reference__icontains=search) |
                Q(description__icontains=search)
            )
        
        return queryset