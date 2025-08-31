# payments/views.py
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.urls import reverse
from decimal import Decimal#, InvalidOperation
from .models import PaymentTransaction
from .services import PaystackService, WebhookService
from .forms import WithdrawalForm
from payments.forms import FundingForm


@login_required
def initiate_funding(request):
    """Initialize wallet funding via Paystack"""
    if request.method == 'POST':
        form = FundingForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']

            paystack_service = PaystackService()
            callback_url = request.build_absolute_uri(
                reverse('payments:payment_callback')
            )

            result = paystack_service.initialize_payment(
                user=request.user,
                amount=amount,   # ✅ Pass original amount, service handles kobo conversion
                callback_url=callback_url
            )

            # ✅ Fixed: Access authorization_url from nested data structure
            if result.get('success'):
                auth_url = result.get('data', {}).get('authorization_url')
                if auth_url:
                    return redirect(auth_url)
                else:
                    messages.error(
                        request,
                        "Payment initialized but no authorization URL was returned. Please try again."
                    )
            else:
                messages.error(request, f"Payment initialization failed: {result.get('error', 'Unknown error')}")

        # Either form invalid or payment init failed → re-render form with errors
        return render(request, "wallets/fund_wallet.html", {"form": form})

    # GET → empty form
    return render(request, "wallets/fund_wallet.html", {"form": FundingForm()})


@login_required
def payment_callback(request):
    """Handle payment callback from Paystack"""
    reference = request.GET.get('reference')

    if not reference:
        messages.error(request, 'Invalid payment reference')
        return redirect('wallets:dashboard')

    try:
        PaymentTransaction.objects.get(
            gateway_reference=reference,
            user=request.user
        )

        # Verify with Paystack
        paystack_service = PaystackService()
        verification = paystack_service.verify_payment(reference)

        if verification.get('success') and verification.get('data', {}).get('data', {}).get('status') == 'success':
            # Wallet will actually be credited via webhook
            messages.success(request, 'Payment successful! Wallet will be credited shortly.')
        else:
            messages.error(request, 'Payment verification failed')

    except PaymentTransaction.DoesNotExist:
        messages.error(request, 'Transaction not found')
    except Exception:
        messages.error(request, 'An error occurred during payment verification')

    return redirect('wallets:dashboard')


@login_required
def withdraw_funds(request):
    """Handle wallet withdrawal requests"""
    if request.method == 'POST':
        form = WithdrawalForm(request.POST)
        
        if form.is_valid():
            try:
                amount = form.cleaned_data['amount']
                bank_code = form.cleaned_data['bank_code']
                account_number = form.cleaned_data['account_number']
                
                # Check user wallet balance (assuming you have wallet service)
                from wallets.services import WalletService
                wallet_balance = WalletService.get_or_create_wallet(request.user)
                
                if amount > wallet_balance:
                    messages.error(request, 'Insufficient wallet balance')
                    return render(request, 'payments/withdraw.html', {'form': form})
                
                if amount < Decimal('100'):  # Minimum withdrawal
                    messages.error(request, 'Minimum withdrawal amount is ₦100')
                    return render(request, 'payments/withdraw.html', {'form': form})
                
                # Verify account number
                paystack_service = PaystackService()
                account_verification = paystack_service.resolve_account_number(
                    account_number, bank_code
                )
                
                if not account_verification or not account_verification.get('status'):
                    messages.error(request, 'Invalid account details')
                    return render(request, 'payments/withdraw.html', {'form': form})
                
                account_name = account_verification['data']['account_name']
                
                # Create transfer recipient
                recipient_result = paystack_service.create_transfer_recipient(
                    request.user, bank_code, account_number
                )
                
                if not recipient_result or not recipient_result.get('status'):
                    messages.error(request, 'Failed to create transfer recipient')
                    return render(request, 'payments/withdraw.html', {'form': form})
                
                recipient_code = recipient_result['data']['recipient_code']
                
                # Debit wallet first
                debit_result = WalletService.debit_wallet(
                    request.user, amount, f"Withdrawal to {account_name}"
                )
                
                if not debit_result['success']:
                    messages.error(request, 'Failed to debit wallet')
                    return render(request, 'payments/withdraw.html', {'form': form})
                
                # Initiate transfer
                transfer_result = paystack_service.initiate_transfer(
                    user=request.user,
                    amount=amount,
                    recipient_code=recipient_code,
                    reason=f"Wallet withdrawal to {account_name}"
                )
                
                if transfer_result['success']:
                    messages.success(request, 
                        f'Withdrawal of ₦{amount:,.2f} to {account_name} initiated successfully!')
                    return redirect('wallets:dashboard')
                else:
                    # Refund wallet if transfer initiation failed
                    WalletService.credit_wallet(
                        request.user, amount, "Refund for failed withdrawal"
                    )
                    messages.error(request, f"Withdrawal failed: {transfer_result['error']}")
                
            except Exception:
                messages.error(request, 'An error occurred during withdrawal')
        
        return render(request, 'payments/withdraw.html', {'form': form})
    
    else:
        form = WithdrawalForm()
        return render(request, 'payments/withdraw.html', {'form': form})



@login_required
def get_banks(request):
    """API endpoint to get list of banks"""
    paystack_service = PaystackService()
    banks = paystack_service.get_banks()
    return JsonResponse({'banks': banks})


@login_required
def verify_account(request):
    """API endpoint to verify bank account"""
    if request.method == 'POST':
        data = json.loads(request.body)
        account_number = data.get('account_number')
        bank_code = data.get('bank_code')

        if not account_number or not bank_code:
            return JsonResponse({'success': False, 'error': 'Missing parameters'})

        paystack_service = PaystackService()
        result = paystack_service.resolve_account_number(account_number, bank_code)

        if result and result.get('status'):
            return JsonResponse({
                'success': True,
                'account_name': result['data']['account_name']
            })
        else:
            return JsonResponse({'success': False, 'error': 'Invalid account details'})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook(request):
    """Handle Paystack webhooks"""
    signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE')

    if not signature:
        return HttpResponse('No signature', status=400)

    if not WebhookService.verify_paystack_signature(request.body, signature):
        return HttpResponse('Invalid signature', status=400)

    try:
        event_data = json.loads(request.body)
        result = WebhookService.process_paystack_webhook(event_data)

        if result['success']:
            return HttpResponse('OK', status=200)
        else:
            return HttpResponse(result['error'], status=400)

    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON', status=400)
    except Exception as e:
        return HttpResponse(f'Internal error: {str(e)}', status=500)



@login_required
def transaction_history(request):
    """Display user's payment transaction history"""
    transactions = PaymentTransaction.objects.filter(
        user=request.user
    ).select_related('gateway').order_by('-created_at')

    return render(request, 'payments/transaction_history.html', {'transactions': transactions})




@login_required
def transaction_detail(request, transaction_id):
    """Display detailed view of a transaction"""
    transaction = get_object_or_404(
        PaymentTransaction,
        id=transaction_id,
        user=request.user
    )
    return render(request, 'payments/transaction_detail.html', {'transaction': transaction})