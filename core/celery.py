# celery.py - Celery configuration
import os
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cc_marketers.settings')

app = Celery('cc_marketers')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery beat schedule for periodic tasks
app.conf.beat_schedule = {
    'process-withdrawals-every-hour': {
        'task': 'wallets.celery_tasks.process_pending_withdrawals',
        'schedule': 60.0 * 60,  # Every hour
    },
    'daily-wallet-audit': {
        'task': 'wallets.celery_tasks.daily_wallet_audit',
        'schedule': 60.0 * 60 * 24,  # Daily
    },
}

app.conf.timezone = 'UTC'
