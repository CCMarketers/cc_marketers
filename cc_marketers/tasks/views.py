
# tasks/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from .models import Task, Submission, Dispute, TaskWallet, TaskWalletTransaction
from .forms import TaskForm, SubmissionForm, TaskFilterForm, DisputeForm, ReviewSubmissionForm
from django.db.models import Count, Q, F, Sum
from users.models import User
from wallets.services import WalletService
from django.views.generic import DetailView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from tasks.services import TaskWalletService
from .forms import TaskWalletTopupForm
from decimal import Decimal
from wallets.models import WithdrawalRequest
from django.views.generic.edit import FormView
from subscriptions.decorators import subscription_required
from wallets.models import EscrowTransaction
from django.db import transaction


@login_required
def task_list(request):
    tasks = Task.objects.filter(
        status='active',
        deadline__gt=timezone.now(),
        remaining_slots__gt=0
    )

    form = TaskFilterForm(request.GET)

    if form.is_valid():
        if form.cleaned_data.get('min_payout'):
            tasks = tasks.filter(payout_per_slot__gte=form.cleaned_data['min_payout'])
        if form.cleaned_data.get('max_payout'):
            tasks = tasks.filter(payout_per_slot__lte=form.cleaned_data['max_payout'])
        if form.cleaned_data.get('search'):
            tasks = tasks.filter(
                Q(title__icontains=form.cleaned_data['search']) |
                Q(description__icontains=form.cleaned_data['search'])
            )

    paginator = Paginator(tasks, 10)
    page = request.GET.get('page')
    tasks = paginator.get_page(page)

    # Calculate progress percentage + check if user already submitted
    for task in tasks:
        task.progress = (task.filled_slots / task.total_slots * 100) if task.total_slots > 0 else 0
        task.already_submitted = Submission.objects.filter(task=task, member=request.user).exists()

    return render(request, 'tasks/task_list.html', {"tasks": tasks, "form": form})

@login_required
@subscription_required
def task_detail(request, task_id):
    """View task details and submit"""
    task = get_object_or_404(Task, id=task_id)

    # Prevent advertisers from doing their own tasks
    if task.advertiser == request.user:
        messages.error(request, "You cannot submit to your own task.")
        return redirect("tasks:task_list")

    existing_submission = Submission.objects.filter(task=task, member=request.user).first()

    form = SubmissionForm(request.POST or None, request.FILES or None) # Initialize form once

    if request.method == 'POST':
        # Check submission conditions again inside the POST block
        if existing_submission:
            messages.error(request, "You have already submitted to this task.")
        elif task.is_full:
            messages.error(request, "This task is already full.")
        elif task.is_expired:
            messages.error(request, "This task has expired.")
        elif form.is_valid():
            submission = form.save(commit=False)
            submission.task = task
            submission.member = request.user
            submission.save()

            # Use F() expression for a race-condition-safe update
            task.remaining_slots = F('remaining_slots') - 1
            task.save()

            messages.success(request, 'Your submission has been received!')
            return redirect('tasks:task_detail', task_id=task.id)
        # If form is invalid or conditions aren't met, the view will fall through
        # to the final render() call, showing the form with errors.

    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'form': form,
        'existing_submission': existing_submission,
    })

@login_required
@subscription_required
def create_task(request):
    if request.user.role != User.ADVERTISER and not request.user.is_staff:
        messages.error(request, "Only advertisers can create tasks.")
        return redirect("tasks:task_list")
    
    if request.method == 'POST':
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
                        amount=total_cost
                    )

                messages.success(request, 'Task created successfully and funds locked in escrow!')
                return redirect('tasks:my_tasks')
            except ValueError as e:
                # Handle insufficient balance (or other business rule violations)
                messages.error(request, str(e))
                return redirect('tasks:task_wallet_topup')
    else:
        form = TaskForm()
    
    return render(request, 'tasks/create_task.html', {'form': form})



@login_required
@subscription_required
def my_tasks(request):
    tasks = (
        Task.objects.filter(advertiser=request.user).order_by('-created_at')
        .annotate(
            pending_count=Count('submissions', filter=Q(submissions__status='pending')),
            approved_count=Count('submissions', filter=Q(submissions__status='approved')),
            rejected_count=Count('submissions', filter=Q(submissions__status='rejected')),
            submissions_count=Count('submissions')  # renamed from filled_slots
        )

    )

    paginator = Paginator(tasks, 10)
    page = request.GET.get("page")
    tasks = paginator.get_page(page)

    return render(request, "tasks/my_tasks.html", {"tasks": tasks})


@login_required
@subscription_required
def delete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, advertiser=request.user)

    if task.submissions.exists():
        messages.error(request, "You cannot delete this task because it already has submissions.")
        return redirect("tasks:my_tasks")

    if request.method == "POST":
        # Refund escrow before deleting
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
        form = TaskForm(request.POST, instance=task)
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
    """View user's task submissions"""
    submissions = Submission.objects.filter(member=request.user).order_by('-reviewed_at')
    paginator = Paginator(submissions, 10)
    page = request.GET.get('page')
    submissions = paginator.get_page(page)
    
    return render(request, 'tasks/my_submissions.html', {'submissions': submissions})

@login_required
@subscription_required
def review_submissions(request, task_id):
    task = get_object_or_404(Task, id=task_id, advertiser=request.user)
    submissions = task.submissions.filter(status="pending").order_by('-reviewed_at')

    # Pre-compute counts
    approved_count = task.submissions.filter(status="approved").count()
    rejected_count = task.submissions.filter(status="rejected").count()

    return render(request, "tasks/review_submissions.html", {
        "task": task,
        "submissions": submissions,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
    })

@login_required
@subscription_required
def review_submission(request, submission_id):
    """Review individual submission (advertiser or staff)"""
    submission = get_object_or_404(Submission, id=submission_id)
    
    if submission.task.advertiser != request.user and not request.user.is_staff:
        messages.error(request, 'Permission denied.')
        return redirect('tasks:task_list')
    
    if request.method == 'POST':
        form = ReviewSubmissionForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data['decision']

            if decision == 'approve':
                submission.approve(request.user)

                # ✅ Release escrow instead of direct wallet credit

                escrow = get_object_or_404(EscrowTransaction, task=submission.task)

                TaskWalletService.release_task_escrow(escrow, submission.member)

                messages.success(request, 'Submission approved and escrow released!')

            elif decision == 'reject':
                reason = form.cleaned_data.get('rejection_reason')
                if not reason:
                    messages.error(request, 'Rejection reason is required.')
                else:
                    submission.reject(request.user, reason)
                    messages.success(request, 'Submission rejected.')

            return redirect('tasks:review_submissions', task_id=submission.task.id)
    else:
        form = ReviewSubmissionForm()
    
    return render(request, 'tasks/review_submission.html', {
        'submission': submission,
        'form': form,
    })


# Dispute Views
@login_required
@subscription_required
def create_dispute(request, submission_id):
    """Create dispute for rejected submission"""
    submission = get_object_or_404(Submission, id=submission_id, member=request.user, status='rejected')
    
    # Check if dispute already exists
    if hasattr(submission, 'dispute'):
        messages.info(request, 'Dispute already exists for this submission.')
        return redirect('tasks:dispute_detail', dispute_id=submission.dispute.id)
    
    if request.method == 'POST':
        form = DisputeForm(request.POST)
        if form.is_valid():
            dispute = form.save(commit=False)
            dispute.submission = submission
            dispute.raised_by = request.user
            dispute.save()
            messages.success(request, 'Dispute created successfully!')
            return redirect('tasks:my_disputes')
    else:
        form = DisputeForm()
    
    return render(request, 'tasks/create_dispute.html', {
        'submission': submission,
        'form': form,
    })

@login_required
@subscription_required
def my_disputes(request):
    """View user's disputes"""
    disputes = Dispute.objects.filter(raised_by=request.user)
    return render(request, 'tasks/my_disputes.html', {'disputes': disputes})

@login_required
@subscription_required
def dispute_detail(request, dispute_id):
    """View dispute details"""
    dispute = get_object_or_404(Dispute, id=dispute_id)
    
    # Check permissions
    if dispute.raised_by != request.user and dispute.submission.task.advertiser != request.user and not request.user.is_staff:
        messages.error(request, 'Permission denied.')
        return redirect('tasks:task_list')
    
    return render(request, 'tasks/dispute_detail.html', {'dispute': dispute})

@staff_member_required
def admin_disputes(request):
    """Admin dashboard for managing disputes"""
    disputes = Dispute.objects.filter(status__in=['open', 'investigating']).order_by('-created_at')
    return render(request, 'tasks/admin_disputes.html', {'disputes': disputes})


@staff_member_required
def resolve_dispute(request, dispute_id):
    """Admin resolve dispute"""
    dispute = get_object_or_404(Dispute, id=dispute_id)
    
    if request.method == 'POST':
        resolution = request.POST.get('resolution')
        admin_notes = request.POST.get('admin_notes', '')

        escrow = EscrowTransaction.objects.filter(task=dispute.submission.task).first()

        if not escrow:
            # No escrow → just mark dispute resolved
            dispute.status = "resolved"
            dispute.resolution = resolution
            dispute.admin_notes = admin_notes
            dispute.save()
            messages.warning(request, "No escrow found for this dispute. Resolved without payout/refund.")
            return redirect("tasks:my_disputes")

                
        if resolution == 'favor_member':
            dispute.status = 'resolved_favor_member'
            dispute.submission.status = 'approved'
            dispute.submission.save()

            # ✅ Release escrow to member
            TaskWalletService.release_task_escrow(escrow, dispute.submission.member)

        elif resolution == 'favor_advertiser':
            dispute.status = 'resolved_favor_advertiser'

            # ✅ Refund advertiser
            TaskWalletService.refund_task_escrow(escrow)
        
        dispute.admin_notes = admin_notes
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.save()
        
        messages.success(request, 'Dispute resolved successfully!')
        return redirect('tasks:admin_disputes')
    
    return render(request, 'tasks/resolve_dispute.html', {'dispute': dispute})


class TaskWalletDashboardView(LoginRequiredMixin, DetailView):
    model = TaskWallet
    template_name = 'tasks/task_wallet_dashboard.html'
    context_object_name = 'task_wallet'

    def get_object(self):
        return TaskWalletService.get_or_create_wallet(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transactions'] = TaskWalletTransaction.objects.filter(
            user=self.request.user
        ).order_by('-created_at')[:10]

        return context


class TaskWalletTransactionListView(LoginRequiredMixin, ListView):
    model = TaskWalletTransaction
    template_name = 'tasks/transactions.html'
    context_object_name = 'transactions'
    paginate_by = 20

    def get_queryset(self):
        return TaskWalletTransaction.objects.filter(user=self.request.user).order_by('-created_at')

class TaskWalletTopupView(LoginRequiredMixin, FormView):
    """Move funds from main wallet into task wallet"""
    form_class = TaskWalletTopupForm
    template_name = 'tasks/topup.html'
    success_url = reverse_lazy('tasks:task_wallet_dashboard')
    
    def form_valid(self, form):
        try:
            TaskWalletService.transfer_from_main_wallet(
                user=self.request.user,
                amount=form.cleaned_data['amount']
            )
            messages.success(
                self.request,
                f"Task Wallet topped up with ${form.cleaned_data['amount']}"
            )
            return redirect(self.success_url)
        except ValueError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        wallet = WalletService.get_or_create_wallet(user)

        pending_withdrawals = WithdrawalRequest.objects.filter(
            user=user, status='pending'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        context['available_balance'] = wallet.get_available_balance() - pending_withdrawals
        return context


