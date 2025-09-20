from pathlib import Path
from decouple import config
import os


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')


# SECURITY WARNING: don't run with debug turned on in production!
#DEBUG = True
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['*']

BACKEND_URL = config('BACKEND_URL')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'crispy_forms',
    'crispy_tailwind',
    "widget_tweaks",

    # Local apps
    'users', 
    'tasks', 
    'referrals', 
    'core',  
    'commerce', 
    'offerwalls',
    'subscriptions',
    'payments',

    "wallets.apps.WalletsConfig",

]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'subscriptions.middleware.SubscriptionMiddleware',
    
]

ROOT_URLCONF = 'cc_marketers.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'subscriptions.context_processors.subscription_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'cc_marketers.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default=5432, cast=int),
        'OPTIONS': {
            'sslmode': config('DB_SSLMODE', default='require'),
        },
    }
}


STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Custom user model
AUTH_USER_MODEL = 'users.User'

# Login/Logout URLs
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

COMPANY_SYSTEM_USERNAME = config('COMPANY_SYSTEM_USERNAME')

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'static/uploads'

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Email Configuration
EMAIL_BACKEND = config('EMAIL_BACKEND')
EMAIL_HOST = config('EMAIL_HOST') 
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "considerateclub@gmail.com")




# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'wallet_system.log',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'wallets': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'tasks': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Payment Gateway Settings
PAYSTACK_PUBLIC_KEY = 'pk_test_your_paystack_public_key'
PAYSTACK_SECRET_KEY = 'sk_test_your_paystack_secret_key'

FLUTTERWAVE_PUBLIC_KEY = 'FLWPUBK_TEST-your_flutterwave_public_key'
FLUTTERWAVE_SECRET_KEY = 'FLWSECK_TEST-your_flutterwave_secret_key'

# Wallet System Settings
WALLET_SETTINGS = {
    'MIN_WITHDRAWAL_AMOUNT': 1.00,
    'MAX_WITHDRAWAL_AMOUNT': 10000.00,
    'DEFAULT_REFERRAL_BONUS': 10.00,
    'CURRENCY': 'USD',
    'CURRENCY_SYMBOL': '$',
}

# Celery settings (for background task processing)
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'




# Paystack Configuration
PAYSTACK_PUBLIC_KEY = 'pk_test_98d1f58ea371bbbfe691ec17b30268cc31ebf7d7'  # Replace with your actual keys
PAYSTACK_SECRET_KEY = 'sk_test_9c232d742d7dddb0b9e808f5427bbc07f76ce702'  # Replace with your actual keys
PAYSTACK_BASE_URL = "https://api.paystack.co"

# For production, use:
# PAYSTACK_PUBLIC_KEY = 'pk_live_your_live_public_key'
# PAYSTACK_SECRET_KEY = 'sk_live_your_live_secret_key'


