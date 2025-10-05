# wallets/apps.py
from django.apps import AppConfig


class WalletsConfig(AppConfig):
    name = "wallets"
    verbose_name = "Wallets"

    def ready(self):
        # Import signals module to register signal handlers
        # Keep import inside ready() to avoid import-time side effects
        from . import signals  # noqa: F401
