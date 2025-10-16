# apps/referrals/apps.py
from django.apps import AppConfig

class ReferralsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'referrals'
    verbose_name = 'Referral System'
    
    def ready(self):
        import referrals.signals

# apps/referrals/__init__.py
# #default_app_config = 'referrals.apps.ReferralsConfig'