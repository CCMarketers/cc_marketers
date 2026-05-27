# management/commands/check_stuck_escrows.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from wallets.models import EscrowTransaction
from decimal import Decimal


class Command(BaseCommand):
    help = "Report any locked escrows on expired tasks"

    def handle(self, *args, **kwargs):
        stuck = EscrowTransaction.objects.filter(
            status="locked",
            task__deadline__lt=timezone.now()
        ).select_related("task", "advertiser")

        if not stuck.exists():
            self.stdout.write(self.style.SUCCESS("✅ No stuck escrows found."))
            return

        total = Decimal('0')
        self.stdout.write(self.style.WARNING(f"⚠️  {stuck.count()} stuck escrows found:\n"))

        for e in stuck:
            self.stdout.write(
                f"  Task: {e.task.title[:40]:<40} | "
                f"₦{e.amount_usd:>10,.2f} | "
                f"Advertiser: {e.advertiser.username}"
            )
            total += e.amount_usd

        self.stdout.write(f"\nTotal at risk: ₦{total:,.2f}")