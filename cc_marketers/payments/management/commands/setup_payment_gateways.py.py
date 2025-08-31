
from django.core.management.base import BaseCommand
from payments.models import PaymentGateway


class Command(BaseCommand):
    help = 'Setup initial payment gateways'

    def handle(self, *args, **options):
        # Create Paystack gateway
        paystack_gateway, created = PaymentGateway.objects.get_or_create(
            name='paystack',
            defaults={
                'is_active': True,
                'config': {
                    'supports_funding': True,
                    'supports_withdrawal': True,
                    'currency': 'NGN',
                    'min_amount': 100,
                    'max_amount': 1000000
                }
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Successfully created Paystack gateway')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Paystack gateway already exists')
            )
        
        # You can add more gateways here in the future
        # Example for Flutterwave:
        # flutterwave_gateway, created = PaymentGateway.objects.get_or_create(
        #     name='flutterwave',
        #     defaults={
        #         'is_active': False,  # Initially inactive
        #         'config': {
        #             'supports_funding': True,
        #             'supports_withdrawal': True,
        #             'currency': 'NGN'
        #         }
        #     }
        # )
        
        self.stdout.write(
            self.style.SUCCESS('Payment gateway setup complete!')
        )