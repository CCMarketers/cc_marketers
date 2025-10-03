from datetime import timedelta
from django.core.management.base import BaseCommand
from payments.models import PaymentTransaction
from payments.services import PaystackService, FlutterwaveService
from django.utils import timezone

class Command(BaseCommand):
    help = 'Reconcile pending payment transactions'

    def handle(self, *args, **options):
        pending_txns = PaymentTransaction.objects.filter(
            status=PaymentTransaction.Status.PENDING,
            transaction_type=PaymentTransaction.TransactionType.FUNDING,
            created_at__gte=timezone.now() - timedelta(days=7)
        )

        for txn in pending_txns:
            try:
                if txn.gateway.name.lower() == "paystack":
                    result = PaystackService().verify_payment(txn.gateway_reference)
                elif txn.gateway.name.lower() == "flutterwave":
                    result = FlutterwaveService().verify_payment_by_reference(txn.gateway_reference)
                
                if result.get("success") and result["data"]["data"]["status"] == "successful":
                    # Process as webhook would
                    self.stdout.write(f"Processed {txn.gateway_reference}")
                    # Trigger webhook handler manually
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error: {e}"))