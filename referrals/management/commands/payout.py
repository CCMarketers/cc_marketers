from decimal import Decimal
from django.db import transaction
from referrals.models import Referral, ReferralEarning
# from wallets.models import 

BONUS_AMOUNT = Decimal("5000.00")

credited_count = 0
skipped_count = 0

for referral in Referral.objects.filter(level=1, is_active=True):
    referrer = referral.referrer
    referred = referral.referred

    # Check if already credited for this referred user
    already_credited = ReferralEarning.objects.filter(
        referrer=referrer,
        referred_user=referred,
        referral=referral,
        earning_type="signup"
    ).exists()

    if already_credited:
        skipped_count += 1
        continue

    with transaction.atomic():
        # Create ReferralEarning record
        earning = ReferralEarning.objects.create(
            referrer=referrer,
            referred_user=referred,
            referral=referral,
            amount=BONUS_AMOUNT,
            earning_type="signup",
            commission_rate=Decimal("100.00"),  # flat bonus
            status="approved",
        )
        credited_count += 1

print(f"✅ {credited_count} direct referrals credited ₦5000 each.")
print(f"⏩ {skipped_count} already credited and skipped.")
