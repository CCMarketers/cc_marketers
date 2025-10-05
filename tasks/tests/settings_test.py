
# tests/settings_test.py
"""
Test settings configuration.
"""
# Test media settings
import tempfile
import os

# Test database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'OPTIONS': {
            'timeout': 20,
        }
    }
}

# Fast password hashing for tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True
    
    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()


TEST_MEDIA_ROOT = os.path.join(tempfile.gettempdir(), 'test_media')
MEDIA_ROOT = TEST_MEDIA_ROOT

# Logging configuration for tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# Email backend for tests
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Cache configuration for tests
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Celery configuration for tests (if using Celery)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

