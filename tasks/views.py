# tasks/views.py

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, F
from django.shortcuts import get_object_or_404, redirect, render
# from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView
# from django.views.generic.edit import FormView

from subscriptions.decorators import subscription_required
from users.models import User
from wallets.models import EscrowTransaction, Wallet
# from wallets.services import WalletService

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import hashlib
from decimal import Decimal, InvalidOperation
import logging
from .forms import (
    DisputeForm,
    ReviewSubmissionForm,
    SubmissionForm,
    TaskFilterForm,
    TaskForm,
    TransactionForm,
)


from .models import Dispute, Submission, Task, TaskWallet, TaskWalletTransaction, TimeWallTransaction
from .services import TaskWalletService
import secrets

from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)




@login_required
def task_list(request):
    """List all active tasks with filtering + pagination."""
    tasks = (
        Task.objects
        .filter(status="active", deadline__gt=timezone.now(), remaining_slots__gt=0)
        .select_related("advertiser", "category")
    )
    form = TaskFilterForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get("min_payout"):
            tasks = tasks.filter(payout_per_slot__gte=form.cleaned_data["min_payout"])
        if form.cleaned_data.get("max_payout"):
            tasks = tasks.filter(payout_per_slot__lte=form.cleaned_data["max_payout"])
        if form.cleaned_data.get("search"):
            search = form.cleaned_data["search"]
            tasks = tasks.filter(Q(title__icontains=search) | Q(description__icontains=search))
        if form.cleaned_data.get("category"):
            tasks = tasks.filter(category=form.cleaned_data["category"])

    paginator = Paginator(tasks, 10)
    page = request.GET.get("page")
    tasks = paginator.get_page(page)

    # annotate per-task state for template
    for task in tasks:
        task.progress = (task.filled_slots / task.total_slots * 100) if task.total_slots else 0
        task.already_submitted = Submission.objects.filter(task=task, member=request.user).exists()

    return render(request, "tasks/task_list.html", {"tasks": tasks, "form": form})

@login_required
@subscription_required
def task_detail(request, task_id):
    """View task details & handle submission POST."""
    task = get_object_or_404(Task.objects.select_related("advertiser"), id=task_id)

    if task.advertiser == request.user:
        messages.error(request, "You cannot submit to your own task.")
        return redirect("tasks:task_list")

    existing_submission = Submission.objects.filter(task=task, member=request.user).first()
    form = SubmissionForm(request.POST or None, request.FILES or None)

    if request.method == "POST":
        if existing_submission:
            messages.error(request, "You have already submitted to this task.")
        elif task.is_full:
            messages.error(request, "This task is already full.")
        elif task.is_expired:
            messages.error(request, "This task has expired.")
        elif form.is_valid():
            with transaction.atomic():
                submission = form.save(commit=False)
                submission.task = task
                submission.member = request.user
                submission.save()

                task.remaining_slots = F("remaining_slots") - 1
                task.save(update_fields=["remaining_slots"])
                task.refresh_from_db(fields=["remaining_slots"])

            messages.success(request, "Your submission has been received!")
            return redirect("tasks:task_detail", task_id=task.id)

    return render(
        request,
        "tasks/task_detail.html",
        {"task": task, "form": form, "existing_submission": existing_submission},
    )
@login_required
@subscription_required
def create_task(request):
    """Advertiser creates a new task; funds locked in escrow."""
    if request.user.account_type != User.MEMBERS and not request.user.is_staff:
        messages.error(request, "Only advertisers can create tasks.")
        return redirect("tasks:task_list")

    if request.method == "POST":
        form = TaskForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    task = form.save(commit=False)
                    task.advertiser = request.user
                    task.remaining_slots = task.total_slots
                    task.save()

                    total_cost = task.payout_per_slot * task.total_slots
                    
                    # ✅ Check if escrow already exists (prevent duplicates)
                    existing_escrow = EscrowTransaction.objects.filter(
                        task=task,
                        status="locked"
                    ).exists()
                    
                    if existing_escrow:
                        raise ValueError("Escrow already created for this task")
                    
                    # ✅ Create escrow ONCE
                    TaskWalletService.create_task_escrow(
                        advertiser=request.user,
                        task=task,
                        amount=total_cost,
                    )

                messages.success(
                    request, "Task created successfully and funds locked in escrow!"
                )
                return redirect("tasks:my_tasks")
            except ValueError as e:
                messages.error(request, str(e))
                return redirect("tasks:transfer_to_task_wallet")
    else:
        form = TaskForm()

    return render(request, "tasks/create_task.html", {"form": form})

@login_required
@subscription_required
def my_tasks(request):
    """List advertiser's own tasks with annotated counts."""
    tasks = (
        Task.objects.filter(advertiser=request.user)
        .select_related("advertiser")
        .annotate(
            pending_count=Count("submissions", filter=Q(submissions__status="pending")),
            approved_count=Count("submissions", filter=Q(submissions__status="approved")),
            rejected_count=Count("submissions", filter=Q(submissions__status="rejected")),
            submissions_count=Count("submissions"),
        )
        .order_by("-created_at")
    )

    paginator = Paginator(tasks, 10)
    page = request.GET.get("page")
    tasks = paginator.get_page(page)
    return render(request, "tasks/my_tasks.html", {"tasks": tasks})


@login_required
@subscription_required
def delete_task(request, task_id):
    """Advertiser deletes a task (refund escrow first)."""
    task = get_object_or_404(Task, id=task_id, advertiser=request.user)

    if task.submissions.exists():
        messages.error(request, "You cannot delete this task because it already has submissions.")
        return redirect("tasks:my_tasks")

    if request.method == "POST":
        escrow = EscrowTransaction.objects.filter(task=task, status="locked").first()
        if escrow:
            TaskWalletService.refund_task_escrow(escrow)

        task.delete()
        messages.success(request, "Task deleted successfully.")
        return redirect("tasks:my_tasks")

    return render(request, "tasks/confirm_delete.html", {"task": task})


@login_required
@subscription_required
def edit_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, advertiser=request.user)

    if task.submissions.exists():
        messages.error(request, "You cannot edit this task because it already has submissions.")
        return redirect("tasks:my_tasks")

    if request.method == "POST":
        form = TaskForm(request.POST, request.FILES, instance=task) 
        if form.is_valid():
            form.save()
            messages.success(request, "Task updated successfully.")
            return redirect("tasks:my_tasks")
    else:
        form = TaskForm(instance=task)

    return render(request, "tasks/edit_task.html", {"form": form, "task": task})

@login_required
@subscription_required
def my_submissions(request):
    submissions = (
        Submission.objects.filter(member=request.user)
        .select_related("task")
        .order_by("-reviewed_at")
    )
    paginator = Paginator(submissions, 10)
    page = request.GET.get("page")
    submissions = paginator.get_page(page)
    return render(request, "tasks/my_submissions.html", {"submissions": submissions})


@login_required
@subscription_required
def review_submissions(request, task_id):
    task = get_object_or_404(Task, id=task_id, advertiser=request.user)
    submissions = task.submissions.filter(status="pending").select_related("member").order_by("-reviewed_at")
    approved_count = task.submissions.filter(status="approved").count()
    rejected_count = task.submissions.filter(status="rejected").count()

    return render(
        request,
        "tasks/review_submissions.html",
        {
            "task": task,
            "submissions": submissions,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
        },
    )

# CRITICAL FIX FOR PRODUCTION RACE CONDITION
# Apply to tasks/views.py → review_submission()

@login_required
@subscription_required
def review_submission(request, submission_id):
    submission = get_object_or_404(
        Submission.objects.select_related("task", "member"), 
        id=submission_id
    )

    if submission.task.advertiser != request.user and not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect("tasks:task_list")

    if request.method == "POST":
        form = ReviewSubmissionForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data["decision"]
            
            if decision == "approve":
                try:
                    with transaction.atomic():
                        # ✅ CRITICAL: Lock submission first to prevent concurrent approvals
                        submission = Submission.objects.select_for_update().get(id=submission_id)
                        
                        # ✅ Check if already approved (race condition check)
                        if submission.status == "approved":
                            messages.warning(request, "This submission has already been approved.")
                            return redirect("tasks:review_submissions", task_id=submission.task.id)
                        
                        # ✅ Lock escrow BEFORE checking (prevents race condition)
                        escrow = EscrowTransaction.objects.select_for_update().filter(
                            task=submission.task, 
                            status="locked"
                        ).first()
                        
                        if not escrow:
                            messages.error(request, "No locked escrow found for this task.")
                            return redirect("tasks:review_submissions", task_id=submission.task.id)
                        
                        # ✅ Update submission status FIRST
                        submission.status = "approved"
                        submission.reviewed_at = timezone.now()
                        submission.reviewed_by = request.user
                        submission.save(update_fields=["status", "reviewed_at", "reviewed_by"])
                        
                        # ✅ Release escrow (escrow already locked above)
                        TaskWalletService.release_task_escrow(escrow, submission.member, submission)
                        
                        messages.success(
                            request, 
                            f"Submission approved! ₦{escrow.task.payout_per_slot * Decimal('0.80')} "
                            f"credited to {submission.member.username}."
                        )
                        
                except ValueError as e:
                    messages.error(request, str(e))
                    logger.error(f"Error approving submission {submission_id}: {e}")
                except Exception as e:
                    messages.error(request, "An error occurred. Please try again.")
                    logger.error(f"Unexpected error approving submission {submission_id}: {e}", exc_info=True)
                    
            elif decision == "reject":
                reason = form.cleaned_data.get("rejection_reason")
                if not reason:
                    messages.error(request, "Rejection reason is required.")
                else:
                    with transaction.atomic():
                        submission.status = "rejected"
                        submission.rejection_reason = reason
                        submission.reviewed_at = timezone.now()
                        submission.reviewed_by = request.user
                        submission.save(update_fields=[
                            "status", "rejection_reason", "reviewed_at", "reviewed_by"
                        ])
                    messages.success(request, "Submission rejected.")
                    
            return redirect("tasks:review_submissions", task_id=submission.task.id)
    else:
        form = ReviewSubmissionForm()
        
    return render(
        request, 
        "tasks/review_submission.html", 
        {"submission": submission, "form": form}
    )


@login_required
@subscription_required
def create_dispute(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, member=request.user, status="rejected")
    if hasattr(submission, "dispute"):
        messages.info(request, "Dispute already exists for this submission.")
        return redirect("tasks:dispute_detail", dispute_id=submission.dispute.id)

    if request.method == "POST":
        form = DisputeForm(request.POST)
        if form.is_valid():
            dispute = form.save(commit=False)
            dispute.submission = submission
            dispute.raised_by = request.user
            dispute.save()
            messages.success(request, "Dispute created successfully!")
            return redirect("tasks:my_disputes")
    else:
        form = DisputeForm()
    return render(request, "tasks/create_dispute.html", {"submission": submission, "form": form})


@login_required
@subscription_required
def my_disputes(request):
    disputes = Dispute.objects.filter(raised_by=request.user).select_related("submission", "submission__task")
    return render(request, "tasks/my_disputes.html", {"disputes": disputes})


@login_required
@subscription_required
def dispute_detail(request, dispute_id):
    dispute = get_object_or_404(
        Dispute.objects.select_related("submission", "submission__task"),
        id=dispute_id,
    )
    if (
        dispute.raised_by != request.user
        and dispute.submission.task.advertiser != request.user
        and not request.user.is_staff
    ):
        messages.error(request, "Permission denied.")
        return redirect("tasks:task_list")
    return render(request, "tasks/dispute_detail.html", {"dispute": dispute})


@staff_member_required
def admin_disputes(request):
    disputes = (
        Dispute.objects.filter(status__in=["open", "investigating"])
        .select_related("submission", "submission__task", "raised_by")
        .order_by("-created_at")
    )
    return render(request, "tasks/admin_disputes.html", {"disputes": disputes})


@staff_member_required
def resolve_dispute(request, dispute_id):
    dispute = get_object_or_404(Dispute.objects.select_related("submission", "submission__task"), id=dispute_id)

    if request.method == "POST":
        resolution = request.POST.get("resolution")
        admin_notes = request.POST.get("admin_notes", "")
        escrow = EscrowTransaction.objects.filter(task=dispute.submission.task, status="locked").first()

        if not escrow:
            dispute.status = "resolved"
            dispute.resolution = resolution
            dispute.admin_notes = admin_notes
            dispute.save()
            messages.warning(request, "No escrow found for this dispute. Resolved without payout/refund.")
            return redirect("tasks:my_disputes")

        with transaction.atomic():
            if resolution == "favor_member":
                dispute.status = "resolved_favor_member"
                dispute.submission.status = "approved"
                dispute.submission.save()
                TaskWalletService.release_task_escrow(escrow, dispute.submission.member)
            elif resolution == "favor_advertiser":
                dispute.status = "resolved_favor_advertiser"
                TaskWalletService.refund_task_escrow(escrow)

            dispute.admin_notes = admin_notes
            dispute.resolved_by = request.user
            dispute.resolved_at = timezone.now()
            dispute.save()

        messages.success(request, "Dispute resolved successfully!")
        return redirect("tasks:admin_disputes")

    return render(request, "tasks/resolve_dispute.html", {"dispute": dispute})



@login_required
@subscription_required
def resubmit_submission(request, submission_id):
    """Allow member to edit and resubmit a previously rejected submission."""
    submission = get_object_or_404(
        Submission.objects.select_related("task"),
        id=submission_id,
        member=request.user,
        status="rejected",
    )
    task = submission.task

    if request.method == "POST":
        form = SubmissionForm(request.POST, request.FILES, instance=submission)
        
        if task.is_expired:
            messages.error(request, "You cannot resubmit — this task has expired.")
            return redirect("tasks:task_detail", task_id=task.id)
        elif task.is_full and submission.task.remaining_slots <= 0:
            messages.error(request, "You cannot resubmit — task slots are full.")
            return redirect("tasks:task_detail", task_id=task.id)
        elif form.is_valid():
            with transaction.atomic():
                updated_submission = form.save(commit=False)
                updated_submission.status = "pending"
                updated_submission.rejection_reason = ""
                updated_submission.reviewed_at = None
                updated_submission.submitted_at = timezone.now()
                updated_submission.save()

            messages.success(request, "Your submission has been resubmitted for review.")
            return redirect("tasks:task_detail", task_id=task.id)
    else:
        form = SubmissionForm(instance=submission)

    # Use a dedicated resubmit template
    return render(
        request,
        "tasks/resubmit_submission.html",
        {
            "task": task,
            "form": form,
            "submission": submission,
        },
    )


class TaskWalletDashboardView(LoginRequiredMixin, DetailView):
    model = TaskWallet
    template_name = "tasks/task_wallet_dashboard.html"
    context_object_name = "task_wallet"

    def get_object(self):
        return TaskWalletService.get_or_create_wallet(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["transactions"] = (
            TaskWalletTransaction.objects.filter(user=self.request.user).order_by("-created_at")[:10]
        )
        return context


class TaskWalletTransactionListView(LoginRequiredMixin, ListView):
    model = TaskWalletTransaction
    template_name = "tasks/transactions.html"
    context_object_name = "transactions"
    paginate_by = 20

    def get_queryset(self):
        return TaskWalletTransaction.objects.filter(user=self.request.user).order_by("-created_at")


# class TaskWalletTopupView(LoginRequiredMixin, FormView):
#     """Move funds from main wallet into task wallet."""
#     form_class = TaskWalletTopupForm
#     template_name = "tasks/topup.html"
#     success_url = reverse_lazy("tasks:task_wallet_dashboard")

#     def form_valid(self, form):
#         try:
#             TaskWalletService.transfer_from_main_wallet(
#                 user=self.request.user, amount=form.cleaned_data["amount"]
#             )
#             messages.success(self.request, f"Task Wallet topped up with ₦{form.cleaned_data['amount']}")
#             return redirect(self.success_url)
#         except ValueError as e:
#             messages.error(self.request, str(e))
#             return self.form_invalid(form)

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         user = self.request.user
#         wallet = WalletService.get_or_create_wallet(user)
#         context["available_balance"] = wallet.get_available_balance()
#         return context


def render_transaction_page(request, form, context_data):
    """Helper function to render transaction pages with common context"""
    context = {
        'form': form,
        **context_data
    }
    return render(request, 'tasks/topup.html', context)

@login_required
def transfer_to_task_wallet_view(request):
    """Transfer funds from main wallet to task wallet"""
    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            try:
                TaskWalletService.transfer_from_main_wallet(request.user, amount)
                messages.success(request, f"₦{amount} successfully transferred to your Task Wallet.")
                return redirect("tasks:task_wallet_dashboard")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception:
                messages.error(request, "Something went wrong while processing your transfer.")
    else:
        form = TransactionForm()

    context = {
        'page_title': 'Top Up Task Wallet',
        'page_description': 'Transfer funds from your main wallet to your task wallet',
        'form_title': 'Transfer Funds',
        'amount_label': 'Transfer Amount',
        'source_balance_label': 'Current Task Wallet Balance',
        'source_balance': request.user.taskwallet.balance,
        'available_balance': Wallet.get_available_balance(), 
        'balance_info_label': 'Main Wallet Balance',
        'transaction_from': 'Main Wallet',
        'transaction_to': 'Task Wallet',
        'transaction_fee': 0,
        'submit_button_text': 'Transfer Funds',
        'quick_amounts': [
            (100, '₦100'),
            (2500, '₦2,500'),
            (5000, '₦5,000'),
            (100000, '₦100,000'),
        ],
        'info_title': 'About Task Wallet Transfers',
        'info_items': [
            'Transfers from your main wallet are instant and free',
            'Funds in your task wallet can only be used for posting tasks',
            'You can transfer any amount above ₦0.01',
            'Your main wallet must have sufficient balance for the transfer',
        ],
    }

    return render_transaction_page(request, form, context)

@login_required
def transfer_to_main_wallet_view(request):
    """Transfer funds from task wallet back to main wallet"""
    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            try:
                result = TaskWalletService.transfer_to_main_wallet(request.user, amount)
                messages.success(request, result["message"])
                return redirect("tasks:task_wallet_dashboard")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception:
                messages.error(request, "Something went wrong while processing your transfer.")
    else:
        form = TransactionForm()

    context = {
        'page_title': 'Withdraw from Task Wallet',
        'page_description': 'Transfer funds from your task wallet back to your main wallet',
        'form_title': 'Withdraw Funds',
        'amount_label': 'Withdrawal Amount',
        'source_balance_label': 'Current Task Wallet Balance',
        'source_balance': request.user.taskwallet.balance,
        'available_balance': request.user.taskwallet.balance,
        'balance_info_label': 'Task Wallet Balance',
        'transaction_from': 'Task Wallet',
        'transaction_to': 'Main Wallet',
        'transaction_fee': 0,
        'submit_button_text': 'Withdraw Funds',
        'quick_amounts': [
            (100, '₦100'),
            (2500, '₦2,500'),
            (5000, '₦5,000'),
            (100000, '₦100,000'),
        ],
        'info_title': 'About Task Wallet Withdrawals',
        'info_items': [
            'Withdrawals to your main wallet are instant and free',
            'You can withdraw any amount above ₦0.01',
            'Your task wallet must have sufficient balance for the withdrawal',
            'Withdrawn funds will be available in your main wallet immediately',
        ],
    }

    return render_transaction_page(request, form, context)



@csrf_exempt
@require_GET
def timewall_postback(request):
    """
    ✅ Secure webhook endpoint for TimeWall postbacks
    Called when a user completes or refunds an offer.
    """
    user_id = request.GET.get("userID")
    transaction_id = request.GET.get("transactionID")
    revenue = request.GET.get("revenue")
    currency_amount = request.GET.get("currencyAmount")
    received_hash = request.GET.get("hash")
    transaction_type = request.GET.get("type", "credit")
    user_ip = request.GET.get("ip", request.META.get("REMOTE_ADDR", ""))

    logger.info(f"[TimeWall] Postback received: UID={user_id}, TXN={transaction_id}, Type={transaction_type}")

    # --- Validate input ---
    if not all([user_id, transaction_id, revenue, currency_amount, received_hash]):
        return JsonResponse({"error": "Missing required parameters"}, status=400)

    # --- Validate secret key ---
    secret = getattr(settings, "TIMEWALL_SECRET_KEY", None)
    if not secret:
        logger.error("TIMEWALL_SECRET_KEY missing in settings.")
        return JsonResponse({"error": "Server misconfiguration"}, status=500)

   # --- Verify hash (SECURITY) ---
    # TimeWall's standard hash is sha1(transactionID-userID-secretKey)
    hash_string = f"{transaction_id}-{user_id}-{secret}"
    expected_hash = hashlib.sha1(hash_string.encode()).hexdigest() # Use sha1, not sha256

    if not secrets.compare_digest(received_hash, expected_hash):
        logger.warning(f"[TimeWall] Invalid hash for UID={user_id}. Expected {expected_hash}, got {received_hash}. Hash string was: {hash_string}")
        return JsonResponse({"error": "Invalid signature"}, status=401)

    # --- Validate user ---
    user = User.objects.filter(id=user_id).first()
    if not user:
        logger.warning(f"[TimeWall] User not found: {user_id}")
        return JsonResponse({"error": "User not found"}, status=404)

    # --- Parse decimal values safely ---
    try:
        points = Decimal(currency_amount)
        revenue_usd = Decimal(revenue)
    except InvalidOperation:
        return JsonResponse({"error": "Invalid numeric format"}, status=400)

    # --- Check for duplicate TXN (idempotency) ---
    if TimeWallTransaction.objects.filter(transaction_id=transaction_id).exists():
        logger.warning(f"[TimeWall] Duplicate TXN ignored: {transaction_id}")
        return JsonResponse({"message": "Duplicate transaction ignored"}, status=200)

    try:
        with transaction.atomic():
            wallet, _ = TaskWallet.objects.get_or_create(user=user)

            if transaction_type == "chargeback":
                TaskWallet.objects.filter(user=user).update(balance=F("balance") - points)
                txn_type = "chargeback"
                note = "TimeWall chargeback – points deducted"
                logger.info(f"[TimeWall] Chargeback processed: -{points} pts for UID={user_id}")
            else:
                TaskWallet.objects.filter(user=user).update(balance=F("balance") + points)
                txn_type = "credit"
                note = f"TimeWall reward earned (${revenue_usd})"
                logger.info(f"[TimeWall] Reward credited: +{points} pts (${revenue_usd}) for UID={user_id}")

            TimeWallTransaction.objects.create(
                user=user,
                transaction_id=transaction_id,
                type=txn_type,
                amount=points if txn_type == "credit" else -points,
                revenue_usd=revenue_usd if txn_type == "credit" else -revenue_usd,
                user_ip=user_ip,
                note=note,
            )

        return JsonResponse({"success": True, "message": "Postback processed"}, status=200)

    except Exception as e:
        logger.error(f"[TimeWall] Processing error for UID={user_id}: {e}", exc_info=True)
        return JsonResponse({"error": "Internal server error"}, status=500)

@login_required
def offerwall_view(request):
    return render(request, "tasks/offerwall.html")