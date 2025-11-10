# referrals/management/commands/process_uncredited_referrals.py

import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from referrals.models import Referral, ReferralEarning
from subscriptions.services import SubscriptionService

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Process uncredited referral commissions for Business Member signups'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be processed without actually crediting',
        )
        parser.add_argument(
            '--user-id',
            type=int,
            help='Process only for a specific user ID',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reprocess even if earnings exist (use with caution)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=100,
            help='Maximum number of users to process (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        user_id = options['user_id']
        force = options['force']
        limit = options['limit']

        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write(self.style.SUCCESS('REFERRAL COMMISSION PROCESSING'))
        self.stdout.write(self.style.SUCCESS('='*70))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No actual changes will be made'))
        
        if force:
            self.stdout.write(self.style.ERROR('⚠️  FORCE MODE - Will reprocess existing earnings!'))
            confirm = input('Are you sure? Type "yes" to continue: ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Aborted.'))
                return

        logger.info(f"[UNCREDITED_CMD] Starting uncredited referral processing (dry_run={dry_run})")

        # Get users to process
        users_to_process = self._get_users_to_process(user_id, limit)
        
        if not users_to_process:
            self.stdout.write(self.style.WARNING('No users found to process.'))
            return

        self.stdout.write(f'\nFound {len(users_to_process)} user(s) to check...\n')

        # Statistics
        stats = {
            'users_checked': 0,
            'users_with_referrals': 0,
            'level_1_credited': 0,
            'level_2_credited': 0,
            'total_amount_credited': Decimal('0.00'),
            'skipped_no_subscription': 0,
            'skipped_demo_account': 0,
            'skipped_already_credited': 0,
            'errors': 0,
        }

        # Process each user
        for user in users_to_process:
            try:
                result = self._process_user(user, dry_run, force)
                stats['users_checked'] += 1
                
                if result['has_referrals']:
                    stats['users_with_referrals'] += 1
                
                stats['level_1_credited'] += result['level_1_credited']
                stats['level_2_credited'] += result['level_2_credited']
                stats['total_amount_credited'] += result['amount_credited']
                stats['skipped_no_subscription'] += result['skipped_no_subscription']
                stats['skipped_demo_account'] += result['skipped_demo_account']
                stats['skipped_already_credited'] += result['skipped_already_credited']
                
            except Exception as e:
                stats['errors'] += 1
                logger.error(
                    f"[UNCREDITED_CMD] Error processing user {user.username}: {str(e)}",
                    exc_info=True
                )
                self.stdout.write(
                    self.style.ERROR(f'❌ Error processing {user.username}: {str(e)}')
                )

        # Print summary
        self._print_summary(stats, dry_run)
        logger.info(f"[UNCREDITED_CMD] Processing complete. Stats: {stats}")

    def _get_users_to_process(self, user_id, limit):
        """Get list of users to process."""
        if user_id:
            # Process specific user
            try:
                user = User.objects.get(id=user_id)
                self.stdout.write(f'Processing specific user: {user.username} (ID: {user.id})')
                return [user]
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User with ID {user_id} not found'))
                return []
        else:
            # Get all users who have been referred (have referrals pointing to them)
            referred_user_ids = Referral.objects.filter(
                is_active=True
            ).values_list('referred_id', flat=True).distinct()
            
            users = User.objects.filter(id__in=referred_user_ids)[:limit]
            return list(users)

    def _process_user(self, user, dry_run, force):
        """Process a single user's referral commissions."""
        result = {
            'has_referrals': False,
            'level_1_credited': 0,
            'level_2_credited': 0,
            'amount_credited': Decimal('0.00'),
            'skipped_no_subscription': 0,
            'skipped_demo_account': 0,
            'skipped_already_credited': 0,
        }

        # Check if user has active subscription
        user_subscription = SubscriptionService.get_user_active_subscription(user)
        
        if not user_subscription:
            result['skipped_no_subscription'] = 1
            self.stdout.write(
                self.style.WARNING(f'⏭️  {user.username}: No active subscription')
            )
            return result

        # Check if user is Business Member
        if user_subscription.plan.name != "Business Member Account":
            result['skipped_demo_account'] = 1
            self.stdout.write(
                self.style.WARNING(
                    f'⏭️  {user.username}: Not a Business Member ({user_subscription.plan.name})'
                )
            )
            return result

        # Get all referrals for this user
        referrals = Referral.objects.filter(
            referred=user,
            is_active=True
        ).select_related('referrer').order_by('level')

        if not referrals.exists():
            return result

        result['has_referrals'] = True
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n👤 {user.username} (Business Member) - '
                f'Found {referrals.count()} referral(s)'
            )
        )

        # Process each referral
        for referral in referrals:
            credit_result = self._credit_referral(user, referral, dry_run, force)
            
            if credit_result['credited']:
                if referral.level == 1:
                    result['level_1_credited'] += 1
                elif referral.level == 2:
                    result['level_2_credited'] += 1
                result['amount_credited'] += credit_result['amount']
            elif credit_result['reason'] == 'already_credited':
                result['skipped_already_credited'] += 1

        return result

    def _credit_referral(self, referred_user, referral, dry_run, force):
        """Credit a single referral commission."""
        result = {
            'credited': False,
            'amount': Decimal('0.00'),
            'reason': None
        }

        referrer = referral.referrer
        
        # Check if already credited (unless force mode)
        if not force:
            existing_earning = ReferralEarning.objects.filter(
                referrer=referrer,
                referred_user=referred_user,
                referral=referral,
                earning_type="signup"
            ).first()
            
            if existing_earning:
                result['reason'] = 'already_credited'
                self.stdout.write(
                    f'  ⏭️  Level {referral.level}: {referrer.username} - '
                    f'Already credited (₦{existing_earning.amount})'
                )
                return result

        # Check if referrer has active subscription
        referrer_subscription = SubscriptionService.get_user_active_subscription(referrer)
        if not referrer_subscription:
            result['reason'] = 'no_referrer_subscription'
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠️  Level {referral.level}: {referrer.username} - '
                    f'No active subscription'
                )
            )
            return result

        # Determine amount based on level
        if referral.level == 1:
            amount = Decimal("5000.00")
        elif referral.level == 2:
            amount = Decimal("3000.00")
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'  ⚠️  Level {referral.level}: {referrer.username} - '
                    f'Unsupported level'
                )
            )
            return result

        # Credit the commission
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'  💰 Level {referral.level}: {referrer.username} - '
                    f'WOULD credit ₦{amount} [DRY RUN]'
                )
            )
            result['credited'] = True
            result['amount'] = amount
        else:
            try:
                with transaction.atomic():
                    earning = ReferralEarning.objects.create(
                        referrer=referrer,
                        referred_user=referred_user,
                        referral=referral,
                        amount=amount,
                        earning_type="signup",
                        commission_rate=Decimal("0.00"),
                        status="approved",
                        approved_at=timezone.now(),
                    )
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✅ Level {referral.level}: {referrer.username} - '
                            f'Credited ₦{amount} (Earning ID: {earning.id})'
                        )
                    )
                    
                    result['credited'] = True
                    result['amount'] = amount
                    
            except Exception as e:
                logger.error(
                    f"[UNCREDITED_CMD] Failed to credit {referrer.username}: {str(e)}",
                    exc_info=True
                )
                self.stdout.write(
                    self.style.ERROR(
                        f'  ❌ Level {referral.level}: {referrer.username} - '
                        f'Error: {str(e)}'
                    )
                )
                result['reason'] = 'error'

        return result

    def _print_summary(self, stats, dry_run):
        """Print processing summary."""
        self.stdout.write('\n' + '='*70)
        self.stdout.write(self.style.SUCCESS('PROCESSING SUMMARY'))
        self.stdout.write('='*70)
        
        self.stdout.write(f"Users checked: {stats['users_checked']}")
        self.stdout.write(f"Users with referrals: {stats['users_with_referrals']}")
        self.stdout.write(f"\nCredits processed:")
        self.stdout.write(f"  Level 1 (Direct): {stats['level_1_credited']}")
        self.stdout.write(f"  Level 2 (Indirect): {stats['level_2_credited']}")
        self.stdout.write(
            self.style.SUCCESS(
                f"  Total amount: ₦{stats['total_amount_credited']:,.2f}"
            )
        )
        
        self.stdout.write(f"\nSkipped:")
        self.stdout.write(f"  No subscription: {stats['skipped_no_subscription']}")
        self.stdout.write(f"  Demo accounts: {stats['skipped_demo_account']}")
        self.stdout.write(f"  Already credited: {stats['skipped_already_credited']}")
        
        if stats['errors'] > 0:
            self.stdout.write(self.style.ERROR(f"\nErrors: {stats['errors']}"))
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  This was a DRY RUN - No actual changes were made'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('\n✅ Processing complete!')
            )