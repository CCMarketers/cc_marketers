from django.core.management.base import BaseCommand
from django.db import transaction
from tasks.models import Submission, TaskWalletTransaction
from tasks.services import TaskWalletService
from wallets.models import EscrowTransaction


class Command(BaseCommand):
    help = "Fix previously released escrows that never credited TaskWallets"

    def handle(self, *args, **options):
        # Fetch approved submissions that might be missing wallet credits
        submissions = (
            Submission.objects.filter(status="approved")
            .select_related("task", "member", "task__advertiser")
        )

        total = submissions.count()
        self.stdout.write(f"🔍 Found {total} approved submissions to verify...")

        fixed, skipped, failed = 0, 0, 0

        for sub in submissions:
            task = sub.task
            member = sub.member

            # Ensure valid task and advertiser
            if not task or not getattr(task, "advertiser", None):
                skipped += 1
                self.stdout.write(f"⚠️  Skipping submission {sub.id}: missing advertiser or task")
                continue

            # Find escrow for this task
            try:
                escrow = EscrowTransaction.objects.get(task=task, advertiser=task.advertiser)
            except EscrowTransaction.DoesNotExist:
                skipped += 1
                continue

            # Only handle escrows that are released
            if escrow.status != "released":
                skipped += 1
                continue

            # Check if already credited
            if self._is_already_credited(member, escrow):
                skipped += 1
                self.stdout.write(f"⏭️  Already credited: {member.username} for task '{task.title}'")
                continue

            # Attempt retroactive credit
            try:
                with transaction.atomic():
                    member_amount, _ = TaskWalletService.split_payment(escrow.amount_usd)

                    TaskWalletService.credit_wallet(
                        user=member,
                        amount=member_amount,
                        category="task_payment",
                        description=f"Retroactive credit for task: {task.title}",
                        reference=str(escrow.id),
                    )

                    # Mark transaction complete in the TaskWalletTransaction table
                    TaskWalletTransaction.objects.filter(
                        user=member,
                        reference=str(escrow.id),
                        category="task_payment"
                    ).update(status="success")

                    fixed += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ Credited {member.username} ₦{member_amount} for task '{task.title}'")
                    )

            except ValueError as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f"❌ Failed to credit {member.username} ({task.title}): {e}")
                )
            except Exception as e:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f"❌ Unexpected error for {member.username} ({task.title}): {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ Done. Fixed: {fixed} | Skipped: {skipped} | Failed: {failed}")
        )

# tasks/management/commands/fix_uncredited_escrows.py

    def _is_already_credited(self, member, escrow):
        """
        Check if worker was already credited for this specific escrow.
        Uses escrow ID as reference to ensure accuracy.
        """
        return TaskWalletTransaction.objects.filter(
            user=member,
            transaction_type="credit",  # Ensure it was a credit
            category="task_payment",
            reference=str(escrow.id)
            # Add status check if applicable, e.g., status="success"
        ).exists()