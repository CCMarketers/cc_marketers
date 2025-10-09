from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from payments.models import PaymentGateway


class Command(BaseCommand):
    help = 'Setup payment gateways (Paystack, Flutterwave, Monnify)'

    def add_arguments(self, parser):
        parser.add_argument(
            'gateway',
            nargs='?',
            type=str,
            choices=['paystack', 'flutterwave', 'monnify', 'all'],
            default='all',
            help='Specify which gateway to setup (default: all)',
        )
        parser.add_argument(
            '--activate',
            action='store_true',
            help='Activate the gateway(s)',
        )
        parser.add_argument(
            '--deactivate',
            action='store_true',
            help='Deactivate the gateway(s)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing gateway configuration',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all payment gateways',
        )

    def get_gateway_config(self, gateway_name):
        """Return configuration for each gateway"""
        configs = {
            'Paystack': {
                'supports_card': True,
                'supports_bank_transfer': True,
                'supports_ussd': True,
                'supports_withdrawal': True,
                'currencies': ['NGN', 'USD', 'GHS', 'ZAR', 'KES'],
                'features': {
                    'split_payment': True,
                    'recurring_payment': True,
                    'refunds': True,
                    'disputes': True,
                },
                'limits': {
                    'min_amount': 100,
                    'max_amount': 50000000,
                }
            },
            'Flutterwave': {
                'supports_card': True,
                'supports_bank_transfer': True,
                'supports_ussd': True,
                'supports_mobile_money': True,
                'supports_withdrawal': True,
                'currencies': ['NGN', 'USD', 'GHS', 'KES', 'UGX', 'TZS', 'ZAR'],
                'features': {
                    'split_payment': True,
                    'recurring_payment': True,
                    'refunds': True,
                    'virtual_cards': True,
                },
                'limits': {
                    'min_amount': 100,
                    'max_amount': 50000000,
                }
            },
            'Monnify': {
                'supports_card': True,
                'supports_bank_transfer': True,
                'supports_ussd': True,
                'supports_withdrawal': True,
                'currencies': ['NGN'],
                'features': {
                    'reserved_accounts': True,
                    'split_payment': True,
                    'recurring_payment': True,
                    'refunds': True,
                },
                'limits': {
                    'min_amount': 100,
                    'max_amount': 50000000,
                }
            }
        }
        return configs.get(gateway_name, {})

    def setup_gateway(self, name, is_active=True, force=False):
        """Setup a single gateway"""
        config = self.get_gateway_config(name)
        
        gateway, created = PaymentGateway.objects.get_or_create(
            name=name,
            defaults={
                'is_active': is_active,
                'config': config,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Created {name} gateway (ID: {gateway.id})')
            )
        else:
            if force:
                gateway.config = config
                gateway.save(update_fields=['config'])
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Updated {name} gateway configuration')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'⚠ {name} gateway already exists (use --force to update)')
                )
        
        return gateway

    def list_gateways(self):
        """List all payment gateways"""
        gateways = PaymentGateway.objects.all().order_by('name')
        
        if not gateways.exists():
            self.stdout.write(self.style.WARNING('No payment gateways found'))
            return

        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.HTTP_INFO('Payment Gateways:'))
        self.stdout.write('='*70)
        
        for gateway in gateways:
            status = self.style.SUCCESS('ACTIVE') if gateway.is_active else self.style.ERROR('INACTIVE')
            self.stdout.write(f'\n{gateway.name} ({status})')
            self.stdout.write(f'  ID: {gateway.id}')
            self.stdout.write(f'  Created: {gateway.created_at}')
            
            if gateway.config:
                currencies = ', '.join(gateway.config.get('currencies', []))
                self.stdout.write(f'  Currencies: {currencies}')
                
                features = []
                if gateway.config.get('supports_card'):
                    features.append('Card')
                if gateway.config.get('supports_bank_transfer'):
                    features.append('Bank Transfer')
                if gateway.config.get('supports_ussd'):
                    features.append('USSD')
                if gateway.config.get('supports_mobile_money'):
                    features.append('Mobile Money')
                if gateway.config.get('supports_withdrawal'):
                    features.append('Withdrawal')
                
                self.stdout.write(f'  Features: {", ".join(features)}')
        
        self.stdout.write('='*70 + '\n')

    @transaction.atomic
    def handle(self, *args, **options):
        gateway_name = options.get('gateway')
        activate = options.get('activate')
        deactivate = options.get('deactivate')
        force = options.get('force')
        list_all = options.get('list')

        # Handle --list flag
        if list_all:
            self.list_gateways()
            return

        # Validate conflicting options
        if activate and deactivate:
            raise CommandError('Cannot use both --activate and --deactivate flags')

        # Determine which gateways to setup
        if gateway_name == 'all':
            gateway_names = ['Paystack', 'Flutterwave', 'Monnify']
        else:
            gateway_names = [gateway_name.capitalize()]

        try:
            # Setup each gateway
            for name in gateway_names:
                gateway = self.setup_gateway(name, is_active=True, force=force)

                # Handle activation/deactivation
                if activate and not gateway.is_active:
                    gateway.is_active = True
                    gateway.save(update_fields=['is_active'])
                    self.stdout.write(self.style.SUCCESS(f'✓ Activated {name}'))
                
                if deactivate and gateway.is_active:
                    gateway.is_active = False
                    gateway.save(update_fields=['is_active'])
                    self.stdout.write(self.style.SUCCESS(f'✓ Deactivated {name}'))

            # Show summary
            self.stdout.write('\n' + self.style.SUCCESS('✓ Setup complete!'))
            self.stdout.write('Run with --list to see all gateways\n')

        except Exception as e:
            raise CommandError(f'Error setting up gateways: {str(e)}')

# python manage.py setup_payments_gateways monnify --activate

# python manage.py setup_payments_gateways all --force

