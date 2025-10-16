from decimal import Decimal
from payments.models import PaymentTransaction
from wallets.models import Wallet, EscrowTransaction, WithdrawalRequest

CONVERSION_RATE = Decimal("1600")

# PaymentTransaction
for txn in PaymentTransaction.objects.all():
    txn.amount_usd = txn.amount_usd / CONVERSION_RATE
    txn.amount_local = txn.amount_local / CONVERSION_RATE
    txn.save(update_fields=["amount_usd", "amount_local"])

# Wallet balances
for wallet in Wallet.objects.all():
    wallet.balance = wallet.balance / CONVERSION_RATE
    wallet.save(update_fields=["balance"])

# Escrow
for escrow in EscrowTransaction.objects.all():
    escrow.amount_usd = escrow.amount_usd / CONVERSION_RATE
    escrow.save(update_fields=["amount_usd"])

# Withdrawals
for wd in WithdrawalRequest.objects.all():
    wd.amount_usd = wd.amount_usd / CONVERSION_RATE
    wd.save(update_fields=["amount_usd"])

print("💲 All wallet-related tables converted back to USD successfully!")
