# wallets/apps.py
from django.apps import AppConfig

class WalletsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'wallets'
    verbose_name = 'Wallet System'
    
    def ready(self):
        # Import signals to ensure they're registered
        import wallets.signals
