# subscriptions/management/commands/create_subscription_plans.py
from django.core.management.base import BaseCommand
from subscriptions.models import SubscriptionPlan


class Command(BaseCommand):
    help = 'Create only Business Member & Demo/Trial subscription plans'

    def handle(self, *args, **options):
        # Clean up old plans
        SubscriptionPlan.objects.exclude(
            plan_type__in=[SubscriptionPlan.PLAN_BUSINESS, SubscriptionPlan.PLAN_TRIAL]
        ).delete()

        # Demo Account (₦1000)
        trial_plan, created = SubscriptionPlan.objects.get_or_create(
            name="Demo Account",
            defaults={
                'plan_type': SubscriptionPlan.PLAN_TRIAL,
                'price': 1000.00,
                'duration_days': 30,

                'own_store': False,
                'hire_marketers': False,
                'affiliate_marketing': False,

                'referral_commission': 0.00,
                'commission_to_tree': 0.00,
                'daily_ad_limit': 100,
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created: {trial_plan.name}'))
        else:
            self.stdout.write(f'Already exists: {trial_plan.name}')

        # Business Member Account (₦20000)
        business_plan, created = SubscriptionPlan.objects.get_or_create(
            name="Business Member Account",
            defaults={
                'plan_type': SubscriptionPlan.PLAN_BUSINESS,
                'price': 20000.00,
                'duration_days': 30,

                'own_store': True,
                'hire_marketers': True,
                'affiliate_marketing': True,

                'referral_commission': 5000.00,
                'commission_to_tree': 3000.00,
                'daily_ad_limit': 0,   # Unlimited
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created: {business_plan.name}'))
        else:
            self.stdout.write(f'Already exists: {business_plan.name}')

        self.stdout.write(self.style.SUCCESS('Subscription plans setup completed!'))
