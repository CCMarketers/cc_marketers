import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from referrals.models import ReferralCode
from subscriptions.services import SubscriptionService

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Ensure all users have referral codes and correct can_refer status'

    def handle(self, *args, **options):
        logger.info("[FIX_CODES] Starting referral code fix...")
        
        created_count = 0
        updated_count = 0
        
        total_users = User.objects.count()
        logger.info(f"[FIX_CODES] Processing {total_users} users...")
        
        for idx, user in enumerate(User.objects.all(), 1):
            if idx % 100 == 0:
                logger.info(f"[FIX_CODES] Progress: {idx}/{total_users}")
            
            # Create referral code if missing
            ref_code, created = ReferralCode.objects.get_or_create(
                user=user,
                defaults={'is_active': True, 'can_refer': True}
            )
            
            if created:
                created_count += 1
                msg = f"✅ Created referral code for {user.username}"
                logger.info(f"[FIX_CODES] {msg}")
                self.stdout.write(self.style.SUCCESS(msg))
            
            # Update can_refer based on subscription
            user_sub = SubscriptionService.get_user_active_subscription(user)
            should_can_refer = bool(user_sub)
            
            if ref_code.can_refer != should_can_refer:
                ref_code.can_refer = should_can_refer
                ref_code.save(update_fields=['can_refer'])
                updated_count += 1
                msg = f"⚙️ Updated can_refer={should_can_refer} for {user.username}"
                logger.info(f"[FIX_CODES] {msg}")
                self.stdout.write(self.style.WARNING(msg))
        
        summary = f'✅ Complete! Created: {created_count}, Updated: {updated_count}'
        logger.info(f"[FIX_CODES] {summary}")
        self.stdout.write(self.style.SUCCESS(f'\n{summary}'))

