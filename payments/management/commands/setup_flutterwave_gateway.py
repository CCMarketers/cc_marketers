
from django.core.management.base import BaseCommand
from payments.models import PaymentGateway

class Command(BaseCommand):
    help = 'Setup Flutterwave payment gateway in database'

    def handle(self, *args, **options):
        gateway, created = PaymentGateway.objects.get_or_create(
            name='flutterwave',
            defaults={
                'is_active': True,
                'config': {
                    'base_url': 'https://api.flutterwave.com/v3',
                    'currency': 'NGN',
                    'min_amount': 50,
                    'max_amount': 1000000,
                }
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Successfully created Flutterwave payment gateway')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Flutterwave payment gateway already exists')
            )