from decimal import Decimal
from tasks.models import Task

CONVERSION_RATE = Decimal("1450")

for task in Task.objects.all():
    task.payout_per_slot = task.payout_per_slot * CONVERSION_RATE
    task.save(update_fields=["payout_per_slot"])

print("✅ All Task payouts converted to ₦ successfully!")
