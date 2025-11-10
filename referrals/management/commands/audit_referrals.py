# referrals/management/commands/audit_referrals.py

import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from referrals.models import Referral, ReferralCode
from subscriptions.services import SubscriptionService

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Audit referral system integrity'

    def handle(self, *args, **options):
        logger.info("[AUDIT] Starting referral system audit...")
        self.stdout.write(self.style.SUCCESS('Starting referral system audit...'))
        
        # Check 1: Invalid Demo → Demo referrals
        logger.info("[AUDIT] Checking for invalid Demo → Demo referrals...")
        invalid_demo_demo = 0
        
        for referral in Referral.objects.filter(is_active=True):
            referrer_sub = SubscriptionService.get_user_active_subscription(referral.referrer)
            referred_sub = SubscriptionService.get_user_active_subscription(referral.referred)
            
            if not referrer_sub or not referred_sub:
                msg = f"⚠️ Referral {referral.id}: Missing subscription"
                logger.warning(f"[AUDIT] {msg}")
                self.stdout.write(self.style.WARNING(msg))
                continue
            
            referrer_type = referrer_sub.plan.name
            referred_type = referred_sub.plan.name
            
            # Check for Demo → Demo (invalid)
            if referrer_type == "Demo Account" and referred_type == "Demo Account":
                msg = (
                    f"❌ Invalid referral {referral.id}: {referral.referrer.username} (Demo) → "
                    f"{referral.referred.username} (Demo)"
                )
                logger.error(f"[AUDIT] {msg}")
                self.stdout.write(self.style.ERROR(msg))
                invalid_demo_demo += 1
        
        # Check 2: Business members exceeding Demo limit
        logger.info("[AUDIT] Checking for Business members exceeding Demo limit...")
        over_limit = 0
        
        for user in User.objects.all():
            user_sub = SubscriptionService.get_user_active_subscription(user)
            if user_sub and user_sub.plan.name == "Business Member Account":
                try:
                    ref_code = user.referral_code
                    demo_count = ref_code.get_active_demo_referral_count()
                    if demo_count > 10:
                        msg = f"❌ {user.username} has {demo_count} Demo referrals (limit: 10)"
                        logger.error(f"[AUDIT] {msg}")
                        self.stdout.write(self.style.ERROR(msg))
                        over_limit += 1
                except ReferralCode.DoesNotExist:
                    pass
        
        # Check 3: Level 3 referrals (should not exist)
        logger.info("[AUDIT] Checking for Level 3 referrals...")
        level_3_count = Referral.objects.filter(level=3).count()
        if level_3_count > 0:
            msg = f"❌ Found {level_3_count} Level 3 referrals (should be deleted)"
            logger.error(f"[AUDIT] {msg}")
            self.stdout.write(self.style.ERROR(msg))
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS('AUDIT SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write(f"Invalid Demo → Demo referrals: {invalid_demo_demo}")
        self.stdout.write(f"Business users over Demo limit: {over_limit}")
        self.stdout.write(f"Level 3 referrals found: {level_3_count}")
        
        if invalid_demo_demo == 0 and over_limit == 0 and level_3_count == 0:
            msg = '✅ Referral system is healthy!'
            logger.info(f"[AUDIT] {msg}")
            self.stdout.write(self.style.SUCCESS(f'\n{msg}'))
        else:
            msg = '⚠️ Issues found! Please review above.'
            logger.warning(f"[AUDIT] {msg}")
            self.stdout.write(self.style.ERROR(f'\n{msg}'))
        
        logger.info("[AUDIT] Audit complete")

