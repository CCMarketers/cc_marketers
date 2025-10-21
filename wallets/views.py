# wallets/views.py
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, CreateView
from django.views.generic.edit import FormView

from .forms import WithdrawalRequestForm, FundWalletForm
from .models import Wallet, WithdrawalRequest, EscrowTransaction
from .services import WalletService
from subscriptions.decorators import subscription_required, plan_required
from payments.services import CurrencyService
from payments.models import PaymentTransaction




class WalletDashboardView(LoginRequiredMixin, DetailView):
    """Main wallet dashboard showing balance, recent transactions."""
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
        context['recent_transactions'] = (
            PaymentTransaction.objects.filter(user=user)
            .select_related('user')
            .order_by('-created_at')[:10]
        )

        # Stats
        context['total_earned'] = PaymentTransaction.objects.filter(
            user=user,
            transaction_type='funding',
            category__in=[
                'task_earning', 'referral_bonus',
                'escrow_release', 'task_payment'
            ]
        ).aggregate(total=Sum('amount_usd'))['total'] or Decimal('0.00')

        context['total_withdrawn'] = PaymentTransaction.objects.filter(
            user=user,
            transaction_type='withdrawal',
            category='withdrawal',
            status='success'
        ).aggregate(total=Sum('amount_usd'))['total'] or Decimal('0.00')

        
        balance_local = CurrencyService.convert_usd_to_local(wallet.balance, user.preferred_currency)

        context['pending_withdrawals'] = wallet.get_pending_withdrawals
        context['wallet_balance'] = wallet.balance
        context['balance_local'] = balance_local
        # Available = wallet.available - pending withdrawals already reserved inside get_available_balance
        context['available_balance'] = wallet.get_available_balance() 

        return context


@method_decorator(subscription_required, name='dispatch')
class TransactionListView(LoginRequiredMixin, ListView):
    """List all user transactions with filters."""
    model = PaymentTransaction
    template_name = 'wallets/transactions.html'
    context_object_name = 'transactions'
    paginate_by = 20

    def get_queryset(self):
        qs = PaymentTransaction.objects.filter(user=self.request.user).select_related('user')

        # Filters
        tx_type = self.request.GET.get('type')
        if tx_type in ['funding', 'withdrawal']:
            qs = qs.filter(transaction_type=tx_type)

        category = self.request.GET.get('category')
        if category:
            qs = qs.filter(category=category)

        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transaction_types'] = PaymentTransaction.TransactionType.choices
        context['transaction_categories'] = PaymentTransaction.Category.choices
        context['transaction_status'] = PaymentTransaction.Status.choices
        return context


@method_decorator(subscription_required, name='dispatch')
@method_decorator(plan_required("Business Member Account"), name="dispatch")
class WithdrawalRequestView(LoginRequiredMixin, CreateView):
    """Create withdrawal request."""
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
                amount=form.cleaned_data['amount_usd'],
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
        context['pending_withdrawals'] = wallet.get_pending_withdrawals
        return context


@method_decorator(subscription_required, name='dispatch')
@method_decorator(plan_required("Business Member Account"), name="dispatch")
class WithdrawalListView(LoginRequiredMixin, ListView):
    """List user's withdrawal requests."""
    model = WithdrawalRequest
    template_name = 'wallets/withdrawal_list.html'
    context_object_name = 'withdrawals'
    paginate_by = 10

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(user=self.request.user).select_related('user')


class FundWalletView(LoginRequiredMixin, FormView):
    """Display wallet funding form."""
    template_name = 'wallets/fund_wallet.html'
    form_class = FundWalletForm
    success_url = reverse_lazy('wallets:dashboard')


@method_decorator(staff_member_required, name='dispatch')
class AdminWithdrawalListView(ListView):
    """Admin view to manage withdrawal requests."""
    model = WithdrawalRequest
    template_name = 'wallets/admin/withdrawal_list.html'
    context_object_name = 'withdrawals'
    paginate_by = 20

    def get_queryset(self):
        qs = WithdrawalRequest.objects.all().select_related('user')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


@method_decorator(staff_member_required, name='dispatch')
class AdminWithdrawalDetailView(DetailView):
    """Admin view to approve/reject withdrawal requests."""
    model = WithdrawalRequest
    template_name = 'wallets/admin/withdrawal_detail.html'
    context_object_name = 'withdrawal'

    def post(self, request, *args, **kwargs):
        withdrawal = self.get_object()
        action = request.POST.get('action')

        try:
            if action == 'approve':
                WalletService.approve_withdrawal(withdrawal.id, request.user)
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
    """Admin view to monitor escrow transactions."""
    model = EscrowTransaction
    template_name = 'wallets/admin/escrow_list.html'
    context_object_name = 'escrows'
    paginate_by = 20

    def get_queryset(self):
        qs = EscrowTransaction.objects.all().select_related('task', 'advertiser')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


from django.db.models import Q
from django.utils.decorators import method_decorator
from django.contrib.admin.views.decorators import staff_member_required
from django.views.generic import ListView
from .models import PaymentTransaction

@method_decorator(staff_member_required, name='dispatch')
class AdminTransactionListView(ListView):
    """Admin view to monitor all transactions."""
    model = PaymentTransaction
    template_name = 'wallets/admin/transaction_list.html'
    context_object_name = 'transactions'
    paginate_by = 50

    def get_queryset(self):
        qs = PaymentTransaction.objects.all().select_related('user')
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(user__username__icontains=search) |
                Q(reference__icontains=search) |
                Q(description__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()

        # Count transactions
        context['total_transactions'] = qs.count()
        context['credits'] = qs.filter(transaction_type='funding', status='success').count()
        context['debits'] = qs.filter(transaction_type='withdrawal', status='success').count()
        context['pending'] = qs.filter(status='pending').count()

        return context




@login_required
def wallet_transaction_detail(request, transaction_id):
    """Display detailed view of a wallet transaction."""
    transaction = get_object_or_404(
        PaymentTransaction,
        id=transaction_id,
        user=request.user
    )
    return render(request, 'wallets/transaction_detail.html', {'transaction': transaction})
