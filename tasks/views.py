# tasks/views.py
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import DetailView, ListView
from django.views.generic.edit import FormView

from subscriptions.decorators import subscription_required
from users.models import User
from wallets.models import WithdrawalRequest, EscrowTransaction
from wallets.services import WalletService

from .forms import (
    DisputeForm,
    ReviewSubmissionForm,
    SubmissionForm,
    TaskFilterForm,
    TaskForm,
    TaskWalletTopupForm,
)
from .models import Dispute, Submission, Task, TaskWallet, TaskWalletTransaction
from .services import TaskWalletService


@login_required
def task_list(request):
    """List all active tasks with filtering + pagination."""
    tasks = (
        Task.objects
        .filter(status="active", deadline__gt=timezone.now(), remaining_slots__gt=0)
        .select_related("advertiser")
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
                return redirect("tasks:task_wallet_topup")
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
        form = TaskForm(request.POST, request.FILES, instance=task)  # ✅ include request.FILES
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
    submission = get_object_or_404(Submission.objects.select_related("task", "member"), id=submission_id)

    if submission.task.advertiser != request.user and not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect("tasks:task_list")

    if request.method == "POST":
        form = ReviewSubmissionForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data["decision"]
            if decision == "approve":
                with transaction.atomic():
                    submission.approve(request.user)
                    escrow = EscrowTransaction.objects.filter(task=submission.task, status="locked").first()
                    if escrow:
                        TaskWalletService.release_task_escrow(escrow, submission.member)
                messages.success(request, "Submission approved and escrow released!")
            elif decision == "reject":
                reason = form.cleaned_data.get("rejection_reason")
                if not reason:
                    messages.error(request, "Rejection reason is required.")
                else:
                    submission.reject(request.user, reason)
                    messages.success(request, "Submission rejected.")
            return redirect("tasks:review_submissions", task_id=submission.task.id)
    else:
        form = ReviewSubmissionForm()
    return render(request, "tasks/review_submission.html", {"submission": submission, "form": form})


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


class TaskWalletTopupView(LoginRequiredMixin, FormView):
    """Move funds from main wallet into task wallet."""
    form_class = TaskWalletTopupForm
    template_name = "tasks/topup.html"
    success_url = reverse_lazy("tasks:task_wallet_dashboard")

    def form_valid(self, form):
        try:
            TaskWalletService.transfer_from_main_wallet(
                user=self.request.user, amount=form.cleaned_data["amount"]
            )
            messages.success(self.request, f"Task Wallet topped up with ${form.cleaned_data['amount']}")
            return redirect(self.success_url)
        except ValueError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        wallet = WalletService.get_or_create_wallet(user)
        pending_withdrawals = (
            WithdrawalRequest.objects.filter(user=user, status="pending").aggregate(total=Sum("amount_usd"))["total"]
            or Decimal("0.00")
        )
        context["available_balance"] = wallet.get_available_balance() - pending_withdrawals
        return context
