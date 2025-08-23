
# tasks/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from .models import Task, Submission, Dispute
from .forms import TaskForm, SubmissionForm, TaskFilterForm, DisputeForm, ReviewSubmissionForm
from django.db.models import Count, Q
from users.models import User

# Task Views
@login_required
def task_list(request):
    tasks = Task.objects.filter(status='active', deadline__gt=timezone.now(), remaining_slots__gt=0)
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

    # Calculate progress percentage for each task
    for task in tasks:
        task.progress = (task.filled_slots / task.total_slots * 100) if task.total_slots > 0 else 0

    return render(request, 'tasks/task_list.html', {"tasks": tasks, "form": form})


@login_required
def task_detail(request, task_id):
    """View task details and submit"""
    task = get_object_or_404(Task, id=task_id)
    
    # Check if user already submitted
    existing_submission = Submission.objects.filter(task=task, member=request.user).first()
    
    if request.method == 'POST' and not existing_submission and not task.is_full and not task.is_expired:
        form = SubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.task = task
            submission.member = request.user
            submission.save()
            
            # Reduce remaining slots
            task.remaining_slots -= 1
            task.save()
            
            messages.success(request, 'Your submission has been received!')
            return redirect('tasks:task_detail', task_id=task.id)
    else:
        form = SubmissionForm()
    
    return render(request, 'tasks/task_detail.html', {
        'task': task,
        'form': form,
        'existing_submission': existing_submission,
    })

@login_required
def create_task(request):
    """Create new task (advertisers only)"""
    if request.user.role != User.ADVERTISER and not request.user.is_staff:
        messages.error(request, "Only advertisers can create tasks.")
        return redirect("tasks:task_list")
    
    if request.method == 'POST':
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.advertiser = request.user
            task.save()
            messages.success(request, 'Task created successfully!')
            return redirect('tasks:my_tasks')
    else:
        form = TaskForm()
    
    return render(request, 'tasks/create_task.html', {'form': form})



# tasks/views.py
@login_required
def my_tasks(request):
    tasks = (
        Task.objects.filter(advertiser=request.user)
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
def my_submissions(request):
    """View user's task submissions"""
    submissions = Submission.objects.filter(member=request.user)
    paginator = Paginator(submissions, 10)
    page = request.GET.get('page')
    submissions = paginator.get_page(page)
    
    return render(request, 'tasks/my_submissions.html', {'submissions': submissions})

# Review Views
@login_required
def review_submissions(request, task_id):
    task = get_object_or_404(Task, id=task_id, advertiser=request.user)
    submissions = task.submissions.filter(status="pending")

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
def review_submission(request, submission_id):
    """Review individual submission"""
    submission = get_object_or_404(Submission, id=submission_id)
    
    # Check permissions
    if submission.task.advertiser != request.user and not request.user.is_staff:
        messages.error(request, 'Permission denied.')
        return redirect('tasks:task_list')
    
    if request.method == 'POST':
        form = ReviewSubmissionForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            if decision == 'approve':
                submission.approve(request.user)
                messages.success(request, 'Submission approved!')
            else:
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
def my_disputes(request):
    """View user's disputes"""
    disputes = Dispute.objects.filter(raised_by=request.user)
    return render(request, 'tasks/my_disputes.html', {'disputes': disputes})

@login_required
def dispute_detail(request, dispute_id):
    """View dispute details"""
    dispute = get_object_or_404(Dispute, id=dispute_id)
    
    # Check permissions
    if dispute.raised_by != request.user and dispute.submission.task.advertiser != request.user and not request.user.is_staff:
        messages.error(request, 'Permission denied.')
        return redirect('tasks:task_list')
    
    return render(request, 'tasks/dispute_detail.html', {'dispute': dispute})

# Admin Views
@staff_member_required
def admin_disputes(request):
    """Admin dashboard for managing disputes"""
    disputes = Dispute.objects.filter(status__in=['open', 'investigating'])
    return render(request, 'tasks/admin_disputes.html', {'disputes': disputes})

@staff_member_required
def resolve_dispute(request, dispute_id):
    """Admin resolve dispute"""
    dispute = get_object_or_404(Dispute, id=dispute_id)
    
    if request.method == 'POST':
        resolution = request.POST.get('resolution')
        admin_notes = request.POST.get('admin_notes', '')
        
        if resolution == 'favor_member':
            dispute.status = 'resolved_favor_member'
            dispute.submission.status = 'approved'
            dispute.submission.save()
        elif resolution == 'favor_advertiser':
            dispute.status = 'resolved_favor_advertiser'
        
        dispute.admin_notes = admin_notes
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.save()
        
        messages.success(request, 'Dispute resolved successfully!')
        return redirect('tasks:admin_disputes')
    
    return render(request, 'tasks/resolve_dispute.html', {'dispute': dispute})
