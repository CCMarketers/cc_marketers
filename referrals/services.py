# apps/referrals/services.py
import logging
from decimal import Decimal
from django.utils import timezone
from .models import Referral, ReferralEarning, ReferralCode

from typing import Optional, Dict, Tuple, TYPE_CHECKING
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

logger = logging.getLogger(__name__)
User = get_user_model()


class ReferralValidator:
    """Validates referral eligibility based on subscription rules."""
    
    DEMO_ACCOUNT = "Demo Account"
    BUSINESS_ACCOUNT = "Business Member Account"
    MAX_DEMO_REFERRALS = 10
    
    @classmethod
    def check_referral_eligibility(
        cls, 
        referral_code: str, 
        new_user_subscription_type: str
    ) -> Dict[str, any]:
        """
        Check if a referral is valid before registration.
        
        Returns dict with:
        - eligible: bool
        - reason: str (if not eligible)
        - referrer_info: dict (if eligible)
        """
        logger.info(
            f"[ELIGIBILITY_CHECK] Checking referral code: {referral_code} "
            f"for subscription: {new_user_subscription_type}"
        )
        
        from subscriptions.services import SubscriptionService
        
        try:
            ref_code = ReferralCode.objects.select_related('user').get(
                code=referral_code, 
                is_active=True
            )
            logger.debug(f"[ELIGIBILITY_CHECK] Found referral code for user: {ref_code.user.username}")
        except ReferralCode.DoesNotExist:
            logger.warning(f"[ELIGIBILITY_CHECK] ❌ Invalid referral code: {referral_code}")
            return {
                "eligible": False,
                "reason": "Invalid or inactive referral code."
            }
        
        referrer = ref_code.user
        
        # Check if referrer can still create referrals
        if not ref_code.can_refer:
            logger.warning(
                f"[ELIGIBILITY_CHECK] ❌ Referral code disabled for: {referrer.username}"
            )
            return {
                "eligible": False,
                "reason": "This referral code is no longer active for new referrals."
            }
        
        # Get referrer's subscription
        referrer_sub = SubscriptionService.get_user_active_subscription(referrer)
        
        if not referrer_sub:
            logger.warning(
                f"[ELIGIBILITY_CHECK] ❌ No active subscription for referrer: {referrer.username}"
            )
            return {
                "eligible": False,
                "reason": "Referrer does not have an active subscription."
            }
        
        referrer_type = referrer_sub.plan.name
        logger.info(
            f"[ELIGIBILITY_CHECK] Referrer type: {referrer_type}, "
            f"New user type: {new_user_subscription_type}"
        )
        
        # RULE 1: Demo can ONLY refer Business
        if referrer_type == cls.DEMO_ACCOUNT:
            if new_user_subscription_type != cls.BUSINESS_ACCOUNT:
                logger.warning(
                    f"[ELIGIBILITY_CHECK] ❌ Demo user {referrer.username} "
                    f"trying to refer {new_user_subscription_type}"
                )
                return {
                    "eligible": False,
                    "reason": f"Demo members can only refer Business Member signups. "
                             f"Please select Business Member subscription or remove the referral code."
                }
            logger.info(f"[ELIGIBILITY_CHECK] ✅ Demo → Business referral allowed")
        
        # RULE 2: Business can refer unlimited Business OR up to 10 active Demo
        elif referrer_type == cls.BUSINESS_ACCOUNT:
            if new_user_subscription_type == cls.DEMO_ACCOUNT:
                # Check the 10 Demo limit
                current_demo_count = ref_code.get_active_demo_referral_count()
                logger.info(
                    f"[ELIGIBILITY_CHECK] Business user {referrer.username} has "
                    f"{current_demo_count}/{cls.MAX_DEMO_REFERRALS} Demo referrals"
                )
                
                if current_demo_count >= cls.MAX_DEMO_REFERRALS:
                    logger.warning(
                        f"[ELIGIBILITY_CHECK] ❌ Demo limit reached for {referrer.username}"
                    )
                    return {
                        "eligible": False,
                        "reason": f"This referrer has reached the maximum limit of {cls.MAX_DEMO_REFERRALS} "
                                 f"active Demo referrals. Please try a different referral code or select "
                                 f"Business Member subscription."
                    }
                logger.info(f"[ELIGIBILITY_CHECK] ✅ Business → Demo referral allowed (within limit)")
            else:
                logger.info(f"[ELIGIBILITY_CHECK] ✅ Business → Business referral allowed")
        
        else:
            logger.error(f"[ELIGIBILITY_CHECK] ❌ Unknown subscription type: {referrer_type}")
            return {
                "eligible": False,
                "reason": f"Unknown referrer subscription type: {referrer_type}"
            }
        
        logger.info(f"[ELIGIBILITY_CHECK] ✅ Referral eligible for {referrer.username}")
        return {
            "eligible": True,
            "referrer_info": {
                "username": referrer.username,
                "display_name": referrer.get_display_name(),
                "subscription_type": referrer_type
            }
        }
    
    @classmethod
    async def check_referral_eligibility_async(cls, referral_code: str, new_user_subscription_type: str):
        """Async version for ASGI support."""
        logger.debug(f"[ELIGIBILITY_CHECK_ASYNC] Processing async check for code: {referral_code}")
        return await sync_to_async(cls.check_referral_eligibility)(
            referral_code, 
            new_user_subscription_type
        )
    
    @classmethod
    def validate_and_create_referral(
        cls,
        new_user,  
        referral_code: str,
        new_user_subscription_type: str
    ) -> Tuple[bool, Optional[Referral], Optional[str]]:
        """
        Validate and create referral relationship.
        
        Returns: (success: bool, referral: Referral|None, error: str|None)
        """
        logger.info(
            f"[REFERRAL_VALIDATE] Validating and creating referral for new user: {new_user.username} "
            f"with code: {referral_code}"
        )
        
        from subscriptions.services import SubscriptionService
        
        # Run eligibility check
        eligibility = cls.check_referral_eligibility(referral_code, new_user_subscription_type)
        
        if not eligibility["eligible"]:
            logger.warning(
                f"[REFERRAL_VALIDATE] ❌ Validation failed for {new_user.username}: "
                f"{eligibility['reason']}"
            )
            return False, None, eligibility["reason"]
        
        try:
            ref_code = ReferralCode.objects.select_related('user').get(
                code=referral_code,
                is_active=True
            )
        except ReferralCode.DoesNotExist:
            logger.error(f"[REFERRAL_VALIDATE] ❌ Referral code not found: {referral_code}")
            return False, None, "Invalid referral code."
        
        referrer = ref_code.user
        
        # Prevent self-referral
        if referrer == new_user:
            logger.warning(
                f"[REFERRAL_VALIDATE] ❌ Self-referral attempt blocked for: {new_user.username}"
            )
            return False, None, "You cannot refer yourself."
        
        # Get referrer subscription type
        referrer_sub = SubscriptionService.get_user_active_subscription(referrer)
        referrer_type = referrer_sub.plan.name if referrer_sub else "Unknown"
        
        # Check if Demo slot is still within limit
        is_within_limits = True
        if (referrer_type == cls.BUSINESS_ACCOUNT and 
            new_user_subscription_type == cls.DEMO_ACCOUNT):
            current_demo_count = ref_code.get_active_demo_referral_count()
            is_within_limits = current_demo_count < cls.MAX_DEMO_REFERRALS
            logger.info(
                f"[REFERRAL_VALIDATE] Demo slot check: {current_demo_count}/{cls.MAX_DEMO_REFERRALS}, "
                f"within_limits: {is_within_limits}"
            )
        
        # Create Level 1 (direct) referral
        try:
            level_1_referral = Referral.objects.create(
                referrer=referrer,
                referred=new_user,
                level=1,
                referral_code=ref_code,
                referrer_subscription_type=referrer_type,
                referred_subscription_type=new_user_subscription_type,
                is_within_limits=is_within_limits
            )
            
            logger.info(
                f"[REFERRAL_VALIDATE] ✅ Level 1 referral created: {referrer.username} → "
                f"{new_user.username} ({referrer_type} → {new_user_subscription_type})"
            )
        except Exception as e:
            logger.error(
                f"[REFERRAL_VALIDATE] ❌ Failed to create Level 1 referral: {str(e)}",
                exc_info=True
            )
            return False, None, f"Failed to create referral: {str(e)}"
        
        # Create Level 2 (indirect) referral if possible
        cls._create_level_2_referral(new_user, referrer, new_user_subscription_type)
        
        return True, level_1_referral, None
    
    @classmethod
    async def validate_and_create_referral_async(cls, new_user, referral_code, new_user_subscription_type):
        """Async version for ASGI support."""
        logger.debug(f"[REFERRAL_VALIDATE_ASYNC] Processing async validation for: {new_user.username}")
        return await sync_to_async(cls.validate_and_create_referral)(
            new_user,
            referral_code,
            new_user_subscription_type
        )
    
    @classmethod
    def _create_level_2_referral(cls, new_user, direct_referrer, new_user_sub_type: str):
        """
        Create Level 2 referral if the direct referrer was also referred.
        
        Chain breaks if:
        - Direct referrer was referred by a Demo AND new user is Demo (Demo can't refer Demo)
        - No Level 1 referral exists for direct referrer
        """
        logger.info(
            f"[LEVEL_2_CHECK] Checking Level 2 eligibility for {new_user.username} "
            f"via {direct_referrer.username}"
        )
        
        from subscriptions.services import SubscriptionService
        
        # Find who referred the direct referrer
        parent_referral = Referral.objects.filter(
            referred=direct_referrer,
            level=1,
            is_active=True
        ).select_related('referrer', 'referral_code').first()
        
        if not parent_referral:
            logger.info(
                f"[LEVEL_2_CHECK] ❌ No Level 2: {direct_referrer.username} has no referrer"
            )
            return
        
        parent_referrer = parent_referral.referrer
        logger.info(f"[LEVEL_2_CHECK] Found parent referrer: {parent_referrer.username}")
        
        # Get parent's subscription type
        parent_sub = SubscriptionService.get_user_active_subscription(parent_referrer)
        if not parent_sub:
            logger.info(
                f"[LEVEL_2_CHECK] ❌ No Level 2: {parent_referrer.username} "
                f"has no active subscription"
            )
            return
        
        parent_type = parent_sub.plan.name
        logger.info(f"[LEVEL_2_CHECK] Parent type: {parent_type}, New user type: {new_user_sub_type}")
        
        # CHAIN BREAK RULE: Demo cannot refer Demo (even indirectly)
        if parent_type == cls.DEMO_ACCOUNT and new_user_sub_type == cls.DEMO_ACCOUNT:
            logger.warning(
                f"[LEVEL_2_CHECK] ❌ Chain break: {parent_referrer.username} (Demo) cannot "
                f"indirectly refer {new_user.username} (Demo)"
            )
            return
        
        # Check parent's referral eligibility
        if parent_type == cls.BUSINESS_ACCOUNT and new_user_sub_type == cls.DEMO_ACCOUNT:
            # Check if parent has Demo slots available
            parent_ref_code = parent_referrer.referral_code
            current_demo_count = parent_ref_code.get_active_demo_referral_count()
            
            logger.info(
                f"[LEVEL_2_CHECK] Parent Demo count: {current_demo_count}/{cls.MAX_DEMO_REFERRALS}"
            )
            
            if current_demo_count >= cls.MAX_DEMO_REFERRALS:
                logger.warning(
                    f"[LEVEL_2_CHECK] ❌ Level 2 skipped: {parent_referrer.username} "
                    f"has reached Demo limit"
                )
                return
        
        # Create Level 2 referral
        try:
            Referral.objects.create(
                referrer=parent_referrer,
                referred=new_user,
                level=2,
                referral_code=parent_referral.referral_code,
                referrer_subscription_type=parent_type,
                referred_subscription_type=new_user_sub_type,
                is_within_limits=True
            )
            
            logger.info(
                f"[LEVEL_2_CHECK] ✅ Level 2 referral created: {parent_referrer.username} → "
                f"{new_user.username} (via {direct_referrer.username})"
            )
        except Exception as e:
            logger.error(
                f"[LEVEL_2_CHECK] ❌ Failed to create Level 2 referral: {str(e)}",
                exc_info=True
            )


class ReferralEarningService:
    """Handles creation of referral earnings."""
    
    # Flat signup bonuses (in local currency)
    LEVEL_1_SIGNUP_BONUS = Decimal("5000.00") 
    LEVEL_2_SIGNUP_BONUS = Decimal("3000.00")  
    
    @classmethod
    def credit_signup_bonus(cls, new_user):  
        """
        Credit signup bonus for Business Member signups ONLY.
        
        Requirements:
        - New user must have Business Member subscription
        - Referrer must have active subscription (Demo or Business)
        - Only credit if no previous signup earning exists
        """
        logger.info(f"[SIGNUP_BONUS] 🎁 Processing signup bonus for: {new_user.username}")
        
        from subscriptions.services import SubscriptionService
        
        if not new_user or not getattr(new_user, "pk", None):
            logger.error("[SIGNUP_BONUS] ❌ Invalid user passed to credit_signup_bonus")
            return
        
        # Prevent duplicate bonuses
        existing_earnings = ReferralEarning.objects.filter(
            referred_user=new_user,
            earning_type="signup"
        )
        
        if existing_earnings.exists():
            logger.warning(
                f"[SIGNUP_BONUS] ⚠️ User {new_user.username} already has {existing_earnings.count()} "
                f"signup earning(s), skipping to prevent duplicate"
            )
            return
        
        # New user MUST be Business Member
        new_user_sub = SubscriptionService.get_user_active_subscription(new_user)
        if not new_user_sub:
            logger.info(
                f"[SIGNUP_BONUS] ❌ User {new_user.username} has no active subscription, "
                f"no signup bonus credited"
            )
            return
        
        if new_user_sub.plan.name != "Business Member Account":
            logger.info(
                f"[SIGNUP_BONUS] ❌ User {new_user.username} is {new_user_sub.plan.name}, "
                f"not Business Member - no signup bonus credited"
            )
            return
        
        # Get all referrals for this user (Level 1 and Level 2)
        referrals = Referral.objects.filter(
            referred=new_user,
            is_active=True
        ).select_related('referrer').order_by('level')
        
        if not referrals.exists():
            logger.info(f"[SIGNUP_BONUS] ℹ️ No active referrals found for {new_user.username}")
            return
        
        logger.info(
            f"[SIGNUP_BONUS] Found {referrals.count()} referral(s) for {new_user.username}: "
            f"{[f'L{r.level}-{r.referrer.username}' for r in referrals]}"
        )
        
        # Credit each referrer based on their level
        credited_count = 0
        for referral in referrals:
            if cls._credit_referrer(referral, new_user):
                credited_count += 1
        
        logger.info(
            f"[SIGNUP_BONUS] ✅ Signup bonus processing complete for {new_user.username}: "
            f"{credited_count}/{referrals.count()} bonuses credited"
        )
    
    @classmethod
    async def credit_signup_bonus_async(cls, new_user):
        """Async version for ASGI support."""
        logger.debug(f"[SIGNUP_BONUS_ASYNC] Processing async bonus credit for: {new_user.username}")
        return await sync_to_async(cls.credit_signup_bonus)(new_user)
    
    @classmethod
    def _credit_referrer(cls, referral: Referral, new_user) -> bool:  
        """
        Credit a single referrer for a Business signup.
        Returns True if successfully credited, False otherwise.
        """
        from subscriptions.services import SubscriptionService
        
        referrer = referral.referrer
        
        logger.info(
            f"[CREDIT_REFERRER] Processing Level {referral.level} bonus for {referrer.username} "
            f"(referred: {new_user.username})"
        )
        
        # Referrer must have active subscription
        referrer_sub = SubscriptionService.get_user_active_subscription(referrer)
        if not referrer_sub:
            logger.warning(
                f"[CREDIT_REFERRER] ❌ {referrer.username} has no active subscription, "
                f"skipping Level {referral.level} bonus"
            )
            return False
        
        logger.debug(
            f"[CREDIT_REFERRER] {referrer.username} has active subscription: "
            f"{referrer_sub.plan.name}"
        )
        
        # Determine bonus amount based on level
        if referral.level == 1:
            amount = cls.LEVEL_1_SIGNUP_BONUS
        elif referral.level == 2:
            amount = cls.LEVEL_2_SIGNUP_BONUS
        else:
            logger.error(f"[CREDIT_REFERRER] ❌ Unsupported referral level: {referral.level}")
            return False
        
        logger.info(
            f"[CREDIT_REFERRER] Bonus amount for Level {referral.level}: ₦{amount}"
        )
        
        # Create the earning
        try:
            earning = ReferralEarning.objects.create(
                referrer=referrer,
                referred_user=new_user,
                referral=referral,
                amount=amount,
                earning_type="signup",
                commission_rate=Decimal("0.00"),
                status="approved",
                approved_at=timezone.now(),
            )
            logger.info(
                f"[CREDIT_REFERRER] ✅ {referrer.username} credited ₦{amount} for referring "
                f"{new_user.username} (Level {referral.level}, Earning ID: {earning.id})"
            )
            return True
            
        except Exception as exc:
            logger.error(
                f"[CREDIT_REFERRER] ❌ Failed to credit {referrer.username}: {str(exc)}",
                exc_info=True
            )
            return False


class ReferralSubscriptionHandler:
    """Handles subscription changes and their impact on referrals."""
    
    @classmethod
    def handle_subscription_upgrade(cls, user, old_plan: str, new_plan: str):  
        """
        Handle user upgrading from Demo to Business.
        
        - Enable referral privileges immediately
        - Grant 10 Demo referral slots
        """
        if old_plan == "Demo Account" and new_plan == "Business Member Account":
            logger.info(
                f"[SUB_UPGRADE] 🎉 {user.username} upgrading from Demo to Business - "
                f"enabling referral privileges"
            )
            
            try:
                referral_code, created = ReferralCode.objects.get_or_create(user=user)
                if created:
                    logger.info(f"[SUB_UPGRADE] Created new referral code for {user.username}")
                
                if not referral_code.can_refer:
                    referral_code.can_refer = True
                    referral_code.save(update_fields=['can_refer'])
                    logger.info(f"[SUB_UPGRADE] Enabled can_refer for {user.username}")
                else:
                    logger.debug(f"[SUB_UPGRADE] can_refer already enabled for {user.username}")
                
                logger.info(
                    f"[SUB_UPGRADE] ✅ {user.username} can now refer 10 Demo + unlimited Business users"
                )
            except Exception as e:
                logger.error(
                    f"[SUB_UPGRADE] ❌ Failed to update referral privileges for {user.username}: {str(e)}",
                    exc_info=True
                )
    
    @classmethod
    async def handle_subscription_upgrade_async(cls, user, old_plan, new_plan):
        """Async version for ASGI support."""
        logger.debug(f"[SUB_UPGRADE_ASYNC] Processing async upgrade for: {user.username}")
        return await sync_to_async(cls.handle_subscription_upgrade)(user, old_plan, new_plan)
    
    @classmethod
    def handle_subscription_downgrade(cls, user, old_plan: str, new_plan: str):  
        """
        Handle user downgrading from Business to Demo.
        
        - Keep existing referral relationships
        - STOP future earnings from those referrals
        - Block new referral creation immediately
        """
        if old_plan == "Business Member Account" and new_plan == "Demo Account":
            logger.warning(
                f"[SUB_DOWNGRADE] ⚠️ {user.username} downgrading from Business to Demo - "
                f"restricting referral privileges"
            )
            
            try:
                referral_code, created = ReferralCode.objects.get_or_create(user=user)
                if created:
                    logger.info(f"[SUB_DOWNGRADE] Created referral code during downgrade for {user.username}")
                
                if referral_code.can_refer:
                    referral_code.can_refer = False
                    referral_code.save(update_fields=['can_refer'])
                    logger.info(f"[SUB_DOWNGRADE] Disabled can_refer for {user.username}")
                else:
                    logger.debug(f"[SUB_DOWNGRADE] can_refer already disabled for {user.username}")
                
                # Count existing referrals
                existing_referrals_count = Referral.objects.filter(
                    referrer=user,
                    is_active=True
                ).count()
                
                logger.info(
                    f"[SUB_DOWNGRADE] ✅ {user.username} blocked from new referrals. "
                    f"Existing {existing_referrals_count} referrals kept but no future earnings"
                )
            except Exception as e:
                logger.error(
                    f"[SUB_DOWNGRADE] ❌ Failed to restrict referral privileges for {user.username}: {str(e)}",
                    exc_info=True
                )
    
    @classmethod
    async def handle_subscription_downgrade_async(cls, user, old_plan, new_plan):
        """Async version for ASGI support."""
        logger.debug(f"[SUB_DOWNGRADE_ASYNC] Processing async downgrade for: {user.username}")
        return await sync_to_async(cls.handle_subscription_downgrade)(user, old_plan, new_plan)
    
    @classmethod
    def handle_subscription_cancellation(cls, user):  
        """
        Handle subscription cancellation.
        
        - Block all referral activities
        - Keep records for historical tracking
        """
        logger.warning(f"[SUB_CANCEL] ❌ {user.username} cancelling subscription - disabling referrals")
        
        try:
            referral_code = user.referral_code
            
            changes = []
            if referral_code.can_refer:
                referral_code.can_refer = False
                changes.append('can_refer')
            # if referral_code.is_active:
            #     referral_code.is_active = False
            #     changes.append('is_active') 
            
            if changes:
                referral_code.save(update_fields=changes)
                logger.info(f"[SUB_CANCEL] Updated fields for {user.username}: {changes}")
            
            logger.info(f"[SUB_CANCEL] ✅ {user.username} referral code deactivated")
            
        except ReferralCode.DoesNotExist:
            logger.warning(f"[SUB_CANCEL] No referral code found for {user.username}")
        except Exception as e:
            logger.error(
                f"[SUB_CANCEL] ❌ Failed to deactivate referral code for {user.username}: {str(e)}",
                exc_info=True
            )
    
    @classmethod
    async def handle_subscription_cancellation_async(cls, user):
        """Async version for ASGI support."""
        logger.debug(f"[SUB_CANCEL_ASYNC] Processing async cancellation for: {user.username}")
        return await sync_to_async(cls.handle_subscription_cancellation)(user)

    
    @classmethod
    def reactivate_referral_code(cls, user):
        """
        ✅ NEW METHOD: Reactivate referral code when user resubscribes.
        
        Called when:
        - User subscribes after cancelling
        - User creates first subscription
        - User reactivates expired subscription
        """
        logger.info(f"[REFERRAL_REACTIVATE] Reactivating referral code for {user.username}")
        
        try:
            referral_code, created = ReferralCode.objects.get_or_create(user=user)
            
            if created:
                logger.info(f"[REFERRAL_REACTIVATE] Created new referral code for {user.username}")
            
            # Reactivate the code
            updates = {}
            if not referral_code.is_active:
                referral_code.is_active = True
                updates['is_active'] = True
                logger.info(f"[REFERRAL_REACTIVATE] Set is_active=True for {user.username}")
            
            if not referral_code.can_refer:
                referral_code.can_refer = True
                updates['can_refer'] = True
                logger.info(f"[REFERRAL_REACTIVATE] Set can_refer=True for {user.username}")
            
            if updates:
                referral_code.save(update_fields=list(updates.keys()))
                logger.info(
                    f"[REFERRAL_REACTIVATE] ✅ Referral code reactivated for {user.username}: {updates}"
                )
            else:
                logger.debug(f"[REFERRAL_REACTIVATE] Referral code already active for {user.username}")
            
        except Exception as e:
            logger.error(
                f"[REFERRAL_REACTIVATE] ❌ Failed to reactivate referral code for {user.username}: {str(e)}",
                exc_info=True
            )
    
    @classmethod
    async def reactivate_referral_code_async(cls, user):
        """Async version for ASGI support."""
        logger.debug(f"[REFERRAL_REACTIVATE_ASYNC] Processing async reactivation for: {user.username}")
        return await sync_to_async(cls.reactivate_referral_code)(user)

