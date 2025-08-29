

# subscriptions/management/commands/create_subscription_plans.py
from django.core.management.base import BaseCommand
from subscriptions.models import SubscriptionPlan

class Command(BaseCommand):
    help = 'Create initial subscription plans'

    def handle(self, *args, **options):
        # Create Marketers Plan
        marketers_plan, created = SubscriptionPlan.objects.get_or_create(
            name="Marketers Plan",
            defaults={
                'price': 10.00,
                'duration_days': 30,
                'business_volume': 0,
                'referral_commission': 5.00,
                'commission_to_tree': 0.00,
                'daily_ad_limit': 100,
                'is_active': True
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created: {marketers_plan.name}')
            )
        else:
            self.stdout.write(
                f'Already exists: {marketers_plan.name}'
            )
        
        # Create Business Member Plan
        business_plan, created = SubscriptionPlan.objects.get_or_create(
            name="Business Member Plan",
            defaults={
                'price': 25.00,
                'duration_days': 30,
                'business_volume': 0,
                'referral_commission': 5.00,
                'commission_to_tree': 0.00,
                'daily_ad_limit': 0,  # 0 means unlimited
                'is_active': True
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'Created: {business_plan.name}')
            )
        else:
            self.stdout.write(
                f'Already exists: {business_plan.name}'
            )
        
        self.stdout.write(
            self.style.SUCCESS('Subscription plans setup completed!')
        )

