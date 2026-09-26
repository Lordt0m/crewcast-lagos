import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present
load_dotenv(BASE_DIR / '.env')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-crewcast-lagos-development-key-2026')
if not DEBUG and (
    not os.getenv('SECRET_KEY')
    or SECRET_KEY.startswith('django-insecure-')
    or SECRET_KEY in {
        'docker-compose-development-key-lagos',
        'insecure-development-key-change-in-production-lagos-weather-planning',
    }
):
    raise ImproperlyConfigured('Set a unique SECRET_KEY before running with DEBUG=False.')

allowed_hosts_env = os.getenv('ALLOWED_HOSTS')
if not DEBUG and not allowed_hosts_env:
    raise ImproperlyConfigured('Set ALLOWED_HOSTS before running with DEBUG=False.')
ALLOWED_HOSTS = [host.strip() for host in (allowed_hosts_env or 'localhost,127.0.0.1,testserver').split(',') if host.strip()]
if not DEBUG and (not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS):
    raise ImproperlyConfigured('ALLOWED_HOSTS must list explicit hostnames when DEBUG=False.')

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'core.middleware.DemoReadOnlyMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'crewcast.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.app_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'crewcast.wsgi.application'

# Database Configuration
# Default to PostgreSQL when DATABASE_URL is set, or fallback to SQLite for quick offline development
DATABASE_URL = os.getenv('DATABASE_URL')
if not DEBUG and not DATABASE_URL:
    raise ImproperlyConfigured('Set a PostgreSQL DATABASE_URL before running with DEBUG=False.')
if DATABASE_URL and not DATABASE_URL.startswith(('postgresql://', 'postgres://')):
    raise ImproperlyConfigured('DATABASE_URL must use a PostgreSQL URL.')

if DATABASE_URL and DATABASE_URL.startswith(('postgresql://', 'postgres://')):
    parsed = urlparse(DATABASE_URL)
    query = parse_qs(parsed.query)
    connection_options = {
        key: query[key][0]
        for key in ('sslmode', 'channel_binding', 'connect_timeout')
        if key in query
    }
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': unquote(parsed.path.lstrip('/')),
            'USER': unquote(parsed.username or ''),
            'PASSWORD': unquote(parsed.password or ''),
            'HOST': parsed.hostname,
            'PORT': parsed.port or 5432,
            'OPTIONS': connection_options,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                'timeout': 20,
            },
        }
    }

# Cache Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'TIMEOUT': 1800, # 30 minutes max TTL
    }
}

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
CELERY_TIMEZONE = 'Africa/Lagos'
CELERY_ENABLE_UTC = True
FORECAST_RUNNER = os.getenv('FORECAST_RUNNER', 'celery')

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
AUTHENTICATION_BACKENDS = ['core.auth.LegacySeedGuardBackend']

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Application specific settings
DAILY_PROVIDER_BUDGET = int(os.getenv('DAILY_PROVIDER_BUDGET', '300'))
DEMO_MODE = os.getenv('DEMO_MODE', 'True').lower() in ('true', '1', 't')
PROVIDER_CIRCUIT_COOLOFF_SECONDS = int(os.getenv('PROVIDER_CIRCUIT_COOLOFF_SECONDS', '900'))
PROVIDER_MAX_RETRIES = int(os.getenv('PROVIDER_MAX_RETRIES', '2'))

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
