
# subscriptions/management/commands/check_subscriptions.py

from django.core.management.base import BaseCommand
from subscriptions.services import SubscriptionService


class Command(BaseCommand):
    help = 'Check and process expired subscriptions'

    def handle(self, *args, **options):
        self.stdout.write('Checking expired subscriptions...')
        SubscriptionService.check_and_renew_subscriptions()
        self.stdout.write(
            self.style.SUCCESS('Successfully processed expired subscriptions')
        )


