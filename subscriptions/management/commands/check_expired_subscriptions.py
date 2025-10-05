
# subscriptions/management/commands/check_expired_subscriptions.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from subscriptions.services import SubscriptionService
from subscriptions.models import UserSubscription

class Command(BaseCommand):
    help = 'Check and process expired subscriptions with auto-renewal'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Get subscriptions that need to be checked
        expired_subscriptions = UserSubscription.objects.filter(
            status='active',
            expiry_date__lte=timezone.now()
        )
        
        self.stdout.write(
            f'Found {expired_subscriptions.count()} expired subscriptions to process'
        )
        
        if not dry_run:
            # Process expired subscriptions
            SubscriptionService.check_and_renew_subscriptions()
            self.stdout.write(
                self.style.SUCCESS('Successfully processed expired subscriptions')
            )
        else:
            # Show what would happen
            for subscription in expired_subscriptions:
                if subscription.auto_renewal:
                    try:
                        from wallets.models import TaskWallet
                        wallet = TaskWallet.objects.get(user=subscription.user)
                        if wallet.balance >= subscription.plan.price:
                            self.stdout.write(
                                f'Would renew: {subscription.user.username} - {subscription.plan.name} (${subscription.plan.price})'
                            )
                        else:
                            self.stdout.write(
                                f'Would expire (insufficient funds): {subscription.user.username} - {subscription.plan.name} (needs ${subscription.plan.price}, has ${wallet.balance})'
                            )
                    except:  # noqa: E722
                        self.stdout.write(
                            f'Would expire (no wallet): {subscription.user.username} - {subscription.plan.name}'
                        )
                else:
                    self.stdout.write(
                        f'Would expire (auto-renewal disabled): {subscription.user.username} - {subscription.plan.name}'
                    )

