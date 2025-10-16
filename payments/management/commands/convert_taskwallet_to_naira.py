# convert_taskwallet_to_naira.py


from decimal import Decimal
from tasks.models import TaskWallet  # adjust the import path if TaskWallet is in another app

CONVERSION_RATE = Decimal("1450")

for tw in TaskWallet.objects.all():
    tw.balance = tw.balance * CONVERSION_RATE
    tw.save(update_fields=["balance"])

print("✅ All TaskWallet balances converted to ₦ successfully!")
