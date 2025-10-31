# tasks/views.py
from chat.models import ChatRoom, Message
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
from wallets.models import EscrowTransaction
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
                # ✅ NEW: CREATE OR GET EXISTING CHAT ROOM BETWEEN ADVERTISER & WORKER
                try:
                    # Get or create ONE chat room for this advertiser-worker pair
                    room, created = ChatRoom.objects.get_or_create(
                        advertiser=task.advertiser,
                        worker=request.user
                    )
                    
                    # Send automatic message about this task
                    Message.objects.create(
                        chat_room=room,
                        sender=request.user,
                        content=f"📋 New submission: I've completed the task '{task.title}'. Please review when you can!"
                    )
                    
                    if created:
                        logger.info(
                            f"[CHAT_CREATED] New chat room created - "
                            f"Advertiser: {task.advertiser.id}, Worker: {request.user.id}"
                        )
                    else:
                        logger.info(
                            f"[CHAT_REUSED] Existing chat room used - "
                            f"Room: {room.id}, New task: {task.id}"
                        )
                    
                except Exception as e:
                    logger.error(
                        f"[CHAT_CREATION_ERROR] Failed to create/get chat room: {e}",
                        exc_info=True
                    )
                    # Don't fail the submission if chat creation fails

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
        logger.warning(
            f"[TASK_CREATE] Unauthorized attempt by user: {request.user.id} ({request.user.email})"
        )
        messages.error(request, "Only advertisers can create tasks.")
        return redirect("tasks:task_list")

    if request.method == "POST":
        form = TaskForm(request.POST, request.FILES)
        logger.info(f"[TASK_CREATE] Form submitted by {request.user.email}")

        if form.is_valid():
            logger.debug(f"[TASK_CREATE] Valid form data received: {form.cleaned_data}")
            try:
                with transaction.atomic():
                    task = form.save(commit=False)
                    task.advertiser = request.user
                    task.remaining_slots = task.total_slots
                    task.save()

                    total_cost = task.payout_per_slot * task.total_slots
                    logger.info(
                        f"[TASK_CREATE] New task created: {task.id} | "
                        f"Advertiser: {request.user.email} | "
                        f"Slots: {task.total_slots} | Total Cost: {total_cost}"
                    )

                    # ✅ Check if escrow already exists (prevent duplicates)
                    existing_escrow = EscrowTransaction.objects.filter(
                        task=task,
                        status="locked"
                    ).exists()

                    if existing_escrow:
                        logger.warning(
                            f"[ESCROW_CREATE] Duplicate escrow attempt for task {task.id}"
                        )
                        raise ValueError("Escrow already created for this task")

                    # ✅ Create escrow ONCE
                    logger.info(
                        f"[ESCROW_CREATE] Creating escrow for Task {task.id} | Amount: {total_cost}"
                    )
                    TaskWalletService.create_task_escrow(
                        advertiser=request.user,
                        task=task,
                        amount=total_cost,
                    )

                logger.info(
                    f"[TASK_CREATE_SUCCESS] Task {task.id} created successfully | Escrow locked: {total_cost}"
                )
                messages.success(
                    request, "Task created successfully and funds locked in escrow!"
                )
                return redirect("tasks:my_tasks")

            except ValueError as e:
                logger.error(
                    f"[TASK_CREATE_ERROR] ValueError for user {request.user.email}: {e}"
                )
                messages.error(request, str(e))
                return redirect("tasks:transfer_to_task_wallet")

            except Exception as e:
                logger.exception(
                    f"[TASK_CREATE_ERROR] Unexpected error for user {request.user.email}: {e}"
                )
                messages.error(request, "An unexpected error occurred.")
                return redirect("tasks:task_list")

        else:
            logger.warning(
                f"[TASK_CREATE] Invalid form submission by {request.user.email}: {form.errors.as_json()}"
            )
    else:
        logger.debug(f"[TASK_CREATE] GET request by {request.user.email}")
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
    """
    ✅ FIXED: Proper escrow refund handling
    """
    task = get_object_or_404(Task, id=task_id, advertiser=request.user)

    if task.submissions.exists():
        messages.error(request, "You cannot delete this task because it already has submissions.")
        return redirect("tasks:my_tasks")

    if request.method == "POST":
        try:
            with transaction.atomic():
                # ✅ Get locked escrow for this task
                escrow = EscrowTransaction.objects.filter(
                    task=task, 
                    status="locked"
                ).select_for_update().first()
                
                if escrow:
                    logger.info(
                        f"[DELETE_TASK] Refunding escrow {escrow.id} for task {task_id}, "
                        f"Amount: {escrow.amount_usd}"
                    )
                    
                    # ✅ Refund escrow back to advertiser's task wallet
                    TaskWalletService.refund_task_escrow(escrow)
                    
                    logger.info(
                        f"[DELETE_TASK] Escrow {escrow.id} refunded successfully"
                    )
                else:
                    logger.info(
                        f"[DELETE_TASK] No locked escrow found for task {task_id}"
                    )
                
                # Delete the task
                task.delete()
                
                messages.success(
                    request, 
                    f"Task deleted successfully. {f'₦{escrow.amount_usd} refunded to your Task Wallet.' if escrow else ''}"
                )
                logger.info(f"[DELETE_TASK] Task {task_id} deleted successfully")
                
        except Exception as e:
            messages.error(request, f"Error deleting task: {str(e)}")
            logger.error(f"[DELETE_TASK] Error deleting task {task_id}: {e}", exc_info=True)
            
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

@login_required
@subscription_required
def review_submission(request, submission_id):
    """
    ✅ FIXED: Proper escrow handling with race condition protection
    """
    submission = get_object_or_404(
        Submission.objects.select_related("task", "member"), 
        id=submission_id
    )
    # Inside your review_submission view
    room = ChatRoom.objects.filter(
        advertiser=submission.task.advertiser,
        worker=submission.member
    ).first()  # returns one room or None


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
                        
                        # ✅ Check if already has escrow release (belt-and-suspenders)
                        if hasattr(submission, 'escrow_release') and submission.escrow_release:
                            messages.warning(
                                request, 
                                f"This submission already has an escrow release (ID: {submission.escrow_release.id})."
                            )
                            return redirect("tasks:review_submissions", task_id=submission.task.id)
                        
                        # ✅ Update submission status FIRST (before escrow release)
                        submission.status = "approved"
                        submission.reviewed_at = timezone.now()
                        submission.reviewed_by = request.user
                        submission.save(update_fields=["status", "reviewed_at", "reviewed_by"])
                        
                        logger.info(
                            f"[APPROVAL] Submission {submission_id} marked approved, "
                            f"releasing escrow for task {submission.task.id}"
                        )
                        
                        # ✅ CORRECT: Pass task object, let service find the escrow
                        TaskWalletService.release_task_escrow(
                            escrow_or_task=submission.task,  # ← FIXED: Pass task, not escrow ID
                            member=submission.member,
                            submission=submission
                        )
                        
                        # Calculate member amount for message
                        member_amount = submission.task.payout_per_slot * Decimal('0.80')
                        
                        messages.success(
                            request, 
                            f"✓ Submission approved! ₦{member_amount} credited to {submission.member.username}."
                        )
                        
                        logger.info(
                            f"[APPROVAL] Successfully approved submission {submission_id}, "
                            f"credited ₦{member_amount} to user {submission.member.id}"
                        )
                        
                except ValueError as e:
                    messages.error(request, f"Payment error: {str(e)}")
                    logger.error(
                        f"[APPROVAL] ValueError for submission {submission_id}: {e}",
                        exc_info=True
                    )
                except Exception as e:
                    messages.error(request, "An unexpected error occurred. Please contact support.")
                    logger.error(
                        f"[APPROVAL] Unexpected error for submission {submission_id}: {e}",
                        exc_info=True
                    )
                    
            elif decision == "reject":
                reason = form.cleaned_data.get("rejection_reason")
                if not reason:
                    messages.error(request, "Rejection reason is required.")
                else:
                    with transaction.atomic():
                        submission = Submission.objects.select_for_update().get(id=submission_id)
                        
                        submission.status = "rejected"
                        submission.rejection_reason = reason
                        submission.reviewed_at = timezone.now()
                        submission.reviewed_by = request.user
                        submission.save(update_fields=[
                            "status", "rejection_reason", "reviewed_at", "reviewed_by"
                        ])
                    
                    logger.info(f"[REJECTION] Submission {submission_id} rejected: {reason}")
                    messages.success(request, "Submission rejected.")
                    
            return redirect("tasks:review_submissions", task_id=submission.task.id)
    else:
        form = ReviewSubmissionForm()
        
    return render(
        request, 
        "tasks/review_submission.html", 
        {"submission": submission, "form": form, "room": room}
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
    """
    ✅ FIXED: Proper escrow handling for dispute resolution
    """
    dispute = get_object_or_404(
        Dispute.objects.select_related("submission", "submission__task"), 
        id=dispute_id
    )

    if request.method == "POST":
        resolution = request.POST.get("resolution")
        admin_notes = request.POST.get("admin_notes", "")
        
        try:
            with transaction.atomic():
                # ✅ CORRECT: Get escrow using the task
                escrow = EscrowTransaction.objects.filter(
                    task=dispute.submission.task, 
                    status="locked"
                ).select_for_update().first()

                if not escrow:
                    logger.warning(
                        f"[DISPUTE] No locked escrow for dispute {dispute_id}, "
                        f"task {dispute.submission.task.id}"
                    )
                    dispute.status = "resolved_no_escrow"
                    dispute.resolution = resolution
                    dispute.admin_notes = admin_notes
                    dispute.resolved_by = request.user
                    dispute.resolved_at = timezone.now()
                    dispute.save()
                    
                    messages.warning(
                        request, 
                        "No locked escrow found for this dispute. Resolved without payout/refund."
                    )
                    return redirect("tasks:admin_disputes")

                if resolution == "favor_member":
                    logger.info(
                        f"[DISPUTE] Resolving in favor of member - "
                        f"Dispute: {dispute_id}, Escrow: {escrow.id}"
                    )
                    
                    dispute.status = "resolved_favor_member"
                    dispute.submission.status = "approved"
                    dispute.submission.save(update_fields=["status"])
                    
                    # ✅ CORRECT: Pass task object
                    TaskWalletService.release_task_escrow(
                        escrow_or_task=dispute.submission.task,  # ← Pass task
                        member=dispute.submission.member,
                        submission=dispute.submission
                    )
                    
                    messages.success(
                        request, 
                        f"Dispute resolved in favor of member. "
                        f"Payment released to {dispute.submission.member.username}."
                    )
                    
                elif resolution == "favor_advertiser":
                    logger.info(
                        f"[DISPUTE] Resolving in favor of advertiser - "
                        f"Dispute: {dispute_id}, Escrow: {escrow.id}"
                    )
                    
                    dispute.status = "resolved_favor_advertiser"
                    
                    # ✅ Refund escrow to advertiser
                    TaskWalletService.refund_task_escrow(escrow)
                    
                    messages.success(
                        request, 
                        "Dispute resolved in favor of advertiser. Escrow refunded."
                    )
                
                else:
                    messages.error(request, "Invalid resolution type.")
                    return redirect("tasks:resolve_dispute", dispute_id=dispute_id)

                dispute.admin_notes = admin_notes
                dispute.resolution = resolution
                dispute.resolved_by = request.user
                dispute.resolved_at = timezone.now()
                dispute.save()
                
                logger.info(
                    f"[DISPUTE] Successfully resolved dispute {dispute_id} - {resolution}"
                )

        except ValueError as e:
            messages.error(request, f"Resolution error: {str(e)}")
            logger.error(f"[DISPUTE] ValueError resolving {dispute_id}: {e}", exc_info=True)
        except Exception as e:
            messages.error(request, "An unexpected error occurred. Please contact support.")
            logger.error(f"[DISPUTE] Error resolving {dispute_id}: {e}", exc_info=True)
            
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
        'available_balance': request.user.wallet.get_available_balance(), 
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
    
    TimeWall Hash Format: SHA256(userID + revenue + SecretKey)
    """
    logger.info("[TimeWallWebhook] Incoming request received", extra={"params": request.GET.dict()})

    # --- IP Whitelist Security ---
    ALLOWED_IPS = ['51.81.120.73', '142.111.248.18']
    
    # Get client IP (handle proxy/load balancer)
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0].strip()
    else:
        client_ip = request.META.get('REMOTE_ADDR', '')
    
    logger.debug(f"[TimeWallWebhook] Client IP: {client_ip}")
    
    if settings.DEBUG:
        logger.warning("[TimeWallWebhook] DEBUG MODE: IP whitelist bypassed")
    else:
        # Verify IP is whitelisted
        if client_ip not in ALLOWED_IPS:
            logger.warning(
                f"[TimeWallWebhook] ⛔ Unauthorized IP blocked: {client_ip}",
                extra={"ip": client_ip, "params": request.GET.dict()}
            )
            return JsonResponse({"error": "Unauthorized IP address"}, status=403)
        
        logger.info(f"[TimeWallWebhook] ✅ IP whitelisted: {client_ip}")

    # --- Extract parameters ---
    user_id = request.GET.get("userID")
    transaction_id = request.GET.get("transactionID")
    revenue = request.GET.get("revenue")
    currency_amount = request.GET.get("currencyAmount")
    received_hash = request.GET.get("hash")
    transaction_type = request.GET.get("type", "credit")
    user_ip = request.GET.get("ip", request.META.get("REMOTE_ADDR", ""))

    logger.debug(
        f"[TimeWallWebhook] Parsed params: "
        f"UID={user_id}, TXN={transaction_id}, Type={transaction_type}, "
        f"IP={user_ip}, Revenue={revenue}, Points={currency_amount}"
    )

    # --- Validate input ---
    if not all([user_id, transaction_id, revenue, currency_amount, received_hash]):
        logger.warning("[TimeWallWebhook] Missing required parameters", extra={"params": request.GET.dict()})
        return JsonResponse({"error": "Missing required parameters"}, status=400)

    # --- Validate secret key ---
    secret = getattr(settings, "TIMEWALL_SECRET_KEY", None)
    if not secret:
        logger.critical("[TimeWallWebhook] TIMEWALL_SECRET_KEY missing in settings.")
        return JsonResponse({"error": "Server misconfiguration"}, status=500)

    # --- Verify hash (SECURITY) ---
    # TimeWall uses: SHA256(userID + revenue + SecretKey)
    hash_string = f"{user_id}{revenue}{secret}"
    expected_hash = hashlib.sha256(hash_string.encode()).hexdigest()

    logger.debug(
        f"[TimeWallWebhook] Hash verification: "
        f"computed={expected_hash}, received={received_hash}, "
        f"base='{user_id}{revenue}[SECRET]'"
    )

    if not secrets.compare_digest(received_hash, expected_hash):
        logger.warning(
            f"[TimeWallWebhook] Invalid hash: "
            f"UID={user_id}, TXN={transaction_id}, "
            f"Expected={expected_hash}, Got={received_hash}"
        )
        return JsonResponse({"error": "Invalid signature"}, status=401)

    # --- Validate user ---
    user = User.objects.filter(id=user_id).first()
    if not user:
        logger.warning(f"[TimeWallWebhook] User not found: UID={user_id}")
        return JsonResponse({"error": "User not found"}, status=404)
    
    logger.info(f"[TimeWallWebhook] User validated: {user.username} (ID={user_id})")

    # --- Parse decimal values safely ---
    try:
        points = Decimal(currency_amount)
        revenue_usd = Decimal(revenue)
        logger.debug(f"[TimeWallWebhook] Parsed decimals: points={points}, revenue_usd={revenue_usd}")
    except (InvalidOperation, ValueError) as e:
        logger.error(
            f"[TimeWallWebhook] Invalid numeric format: "
            f"revenue={revenue}, currencyAmount={currency_amount}, error={e}"
        )
        return JsonResponse({"error": "Invalid numeric format"}, status=400)

    # --- Check for duplicate TXN (idempotency) ---
    if TimeWallTransaction.objects.filter(transaction_id=transaction_id).exists():
        logger.info(f"[TimeWallWebhook] Duplicate TXN ignored: TXN={transaction_id}, UID={user_id}")
        return JsonResponse({"message": "Duplicate transaction ignored"}, status=200)

    logger.info(f"[TimeWallWebhook] Processing new transaction: TXN={transaction_id}, Type={transaction_type}")

    # --- Main processing ---
    try:
        with transaction.atomic():
            wallet, _ = TaskWallet.objects.get_or_create(user=user)
            logger.debug(f"[TimeWallWebhook] Wallet loaded: User={user.username}, Balance={wallet.balance}")

            # Handle chargebacks (negative amounts)
            if transaction_type.lower() == "chargeback" or points < 0 or revenue_usd < 0:
                # Make values absolute for storage
                points_abs = abs(points)
                revenue_abs = abs(revenue_usd)
                
                TaskWallet.objects.filter(user=user).update(balance=F("balance") - points_abs)
                txn_type = "chargeback"
                note = f"TimeWall chargeback – {points_abs} points deducted"
                
                logger.info(f"[TimeWallWebhook] Chargeback processed: UID={user_id}, -{points_abs} pts")
                
                # Store as negative amount
                TimeWallTransaction.objects.create(
                    user=user,
                    transaction_id=transaction_id,
                    type=txn_type,
                    amount=-points_abs,
                    revenue_usd=-revenue_abs,
                    user_ip=user_ip,
                    note=note,
                )
            else:
                # Credit (positive transaction)
                TaskWallet.objects.filter(user=user).update(balance=F("balance") + points)
                txn_type = "credit"
                note = f"TimeWall reward earned (${revenue_usd} revenue)"
                
                logger.info(f"[TimeWallWebhook] Credit processed: UID={user_id}, +{points} pts (${revenue_usd})")
                
                TimeWallTransaction.objects.create(
                    user=user,
                    transaction_id=transaction_id,
                    type=txn_type,
                    amount=points,
                    revenue_usd=revenue_usd,
                    user_ip=user_ip,
                    note=note,
                )

            logger.info(f"[TimeWallWebhook] Transaction saved: TXN={transaction_id}, UID={user_id}, Type={txn_type}")

        logger.info(f"[TimeWallWebhook] ✅ Successfully processed: UID={user_id}, TXN={transaction_id}")
        return JsonResponse({"success": True, "message": "Postback processed"}, status=200)

    except Exception as e:
        logger.exception(f"[TimeWallWebhook] ❌ Error processing TXN={transaction_id}, UID={user_id}: {str(e)}")
        return JsonResponse({"error": "Internal server error"}, status=500)


@login_required
def offerwall_view(request):
    """Display the TimeWall offerwall page"""
    logger.info(f"[TimeWall] Offerwall viewed by UID={request.user.id} ({request.user.username})")
    return render(request, "tasks/offerwall.html")

@login_required
def task_wallet_balance(request):
    wallet, _ = TaskWallet.objects.get_or_create(user=request.user)
    return JsonResponse({
        'balance': float(wallet.balance),
        'user_id': request.user.id,
    })


    

# def complete_task(request, task_id):
#     task = get_object_or_404(Task, id=task_id)
    
#     # Mark task as complete
#     task.status = 'completed'
#     task.save()
    
#     # Get or create chat room
#     room, created = ChatRoom.objects.get_or_create(
#         advertiser=task.advertiser,  # User who posted the task
#         worker=task.worker  # User who completed the task
#     )
    
#     # Link task to chat room
#     task.chat_room = room
#     task.save()
    
#     # Optional: Send an automatic message
#     Message.objects.create(
#         chat_room=room,
#         sender=request.user,
#         content=f"Task '{task.title}' has been completed!"
#     )
    
#     # Redirect to chat room
#     return redirect('chat:room', room_id=room.id)


@login_required
@subscription_required
def chat_with_advertiser(request, task_id):
    """
    Open chat with the advertiser of a specific task.
    Uses the same chat room for ALL tasks between this advertiser-worker pair.
    """
    task = get_object_or_404(
        Task.objects.select_related('advertiser'), 
        id=task_id
    )
    
    # Check if user has submitted to this task
    has_submitted = Submission.objects.filter(
        task=task,
        member=request.user
    ).exists()
    
    # Check if user is the advertiser
    is_advertiser = task.advertiser == request.user
    
    if not (is_advertiser or has_submitted or request.user.is_staff):
        messages.error(request, "You need to submit to this task before chatting with the advertiser.")
        return redirect("tasks:task_detail", task_id=task.id)
    
    # Get or create the chat room for this advertiser-worker pair
    if is_advertiser:
        # Advertiser wants to chat - need to know which worker
        # Get first submission to determine worker
        submission = task.submissions.first()
        if not submission:
            messages.error(request, "No submissions yet for this task.")
            return redirect("tasks:my_tasks")
        other_user = submission.member
    else:
        # Worker wants to chat with advertiser
        other_user = task.advertiser
    
    # Get or create ONE chat room for this pair
    if is_advertiser:
        room, _ = ChatRoom.objects.get_or_create(
            advertiser=request.user,
            worker=other_user
        )
    else:
        room, _ = ChatRoom.objects.get_or_create(
            advertiser=other_user,
            worker=request.user
        )
    
    # Redirect to the chat room
    return redirect('chat:room', room_id=room.id)
