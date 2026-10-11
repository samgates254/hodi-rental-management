import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env')

DJANGO_ENV = os.environ.get('DJANGO_ENV', 'development').strip().lower()
if DJANGO_ENV not in {'development', 'production'}:
    raise ImproperlyConfigured('DJANGO_ENV must be development or production.')

debug_value = os.environ.get('DJANGO_DEBUG')
if DJANGO_ENV == 'production' and debug_value is None:
    raise ImproperlyConfigured('DJANGO_DEBUG must be explicitly set in production.')
debug_value = (debug_value or 'True').strip().lower()
if debug_value not in {'1', '0', 'true', 'false', 'yes', 'no'}:
    raise ImproperlyConfigured('DJANGO_DEBUG must be a boolean value.')
DEBUG = debug_value in {'1', 'true', 'yes'}
if DJANGO_ENV == 'production' and DEBUG:
    raise ImproperlyConfigured('DJANGO_DEBUG must be false in production.')

secret_key = os.environ.get('DJANGO_SECRET_KEY')
if not secret_key and DJANGO_ENV == 'production':
    raise ImproperlyConfigured('DJANGO_SECRET_KEY is required in production.')
SECRET_KEY = secret_key or 'django-insecure-local-only'
if DJANGO_ENV == 'production' and (
    len(SECRET_KEY) < 50
    or any(marker in SECRET_KEY.lower() for marker in ('django-insecure', 'replace-with', 'change-me'))
):
    raise ImproperlyConfigured('Production DJANGO_SECRET_KEY must be a strong generated secret.')

allowed_hosts_value = os.environ.get('DJANGO_ALLOWED_HOSTS')
if DJANGO_ENV == 'production' and not allowed_hosts_value:
    raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS is required in production.')
ALLOWED_HOSTS = [
    host.strip()
    for host in (allowed_hosts_value or 'localhost,127.0.0.1').split(',')
    if host.strip()
]
# Django's test client / APIClient uses Host: testserver by default.
if DJANGO_ENV != 'production' and 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')
if DJANGO_ENV == 'production' and ('*' in ALLOWED_HOSTS or not ALLOWED_HOSTS):
    raise ImproperlyConfigured('Production DJANGO_ALLOWED_HOSTS must contain explicit hosts.')

INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'apps.accounts', 'apps.organizations', 'apps.properties', 'apps.tenants',
    'apps.leases', 'apps.billing', 'apps.maintenance', 'apps.notifications', 'apps.audit',
    'apps.marketplace',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {'default': {
    'ENGINE': os.environ.get('DB_ENGINE', 'django.db.backends.sqlite3'),
    'NAME': os.environ.get('DB_NAME', str(BASE_DIR / 'db.sqlite3')),
    'USER': os.environ.get('DB_USER', ''), 'PASSWORD': os.environ.get('DB_PASSWORD', ''),
    'HOST': os.environ.get('DB_HOST', ''), 'PORT': os.environ.get('DB_PORT', ''),
}}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
EMAIL_VERIFICATION_TOKEN_MAX_AGE = int(
    os.environ.get('EMAIL_VERIFICATION_TOKEN_MAX_AGE', '86400'),
)
if EMAIL_VERIFICATION_TOKEN_MAX_AGE <= 0:
    raise ImproperlyConfigured('EMAIL_VERIFICATION_TOKEN_MAX_AGE must be positive.')
PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', '3600'))
if PASSWORD_RESET_TIMEOUT <= 0:
    raise ImproperlyConfigured('PASSWORD_RESET_TIMEOUT must be positive.')
ACCOUNT_EMAIL_VERIFICATION_PATH = '/api/v1/accounts/verify-email/'
ACCOUNT_PASSWORD_RESET_CONFIRM_PATH = '/api/v1/accounts/password-reset/confirm/'

if DJANGO_ENV == 'production':
    email_host = os.environ.get('DJANGO_EMAIL_HOST')
    default_from_email = os.environ.get('DJANGO_DEFAULT_FROM_EMAIL')
    if not email_host or not default_from_email:
        raise ImproperlyConfigured(
            'DJANGO_EMAIL_HOST and DJANGO_DEFAULT_FROM_EMAIL are required in production.',
        )
    cache_backend = os.environ.get('DJANGO_CACHE_BACKEND')
    cache_location = os.environ.get('DJANGO_CACHE_LOCATION')
    if not cache_backend or not cache_location:
        raise ImproperlyConfigured(
            'DJANGO_CACHE_BACKEND and DJANGO_CACHE_LOCATION are required in production.',
        )
    shared_cache_backends = (
        'redis',
        'memcached',
        'django.core.cache.backends.db.DatabaseCache',
    )
    if not any(backend in cache_backend for backend in shared_cache_backends):
        raise ImproperlyConfigured('Production throttling requires a shared cache backend.')
    CACHES = {
        'default': {
            'BACKEND': cache_backend,
            'LOCATION': cache_location,
        },
    }
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = email_host
    EMAIL_PORT = int(os.environ.get('DJANGO_EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.environ.get('DJANGO_EMAIL_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('DJANGO_EMAIL_PASSWORD', '')
    EMAIL_USE_TLS = os.environ.get('DJANGO_EMAIL_USE_TLS', 'True').lower() in {'1', 'true', 'yes'}
    EMAIL_USE_SSL = os.environ.get('DJANGO_EMAIL_USE_SSL', 'False').lower() in {'1', 'true', 'yes'}
    DEFAULT_FROM_EMAIL = default_from_email
    if EMAIL_USE_TLS and EMAIL_USE_SSL:
        raise ImproperlyConfigured('Use either DJANGO_EMAIL_USE_TLS or DJANGO_EMAIL_USE_SSL, not both.')
    if not EMAIL_USE_TLS and not EMAIL_USE_SSL:
        raise ImproperlyConfigured('Production email transport must use TLS or SSL.')
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        },
    }
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = os.environ.get('DJANGO_DEFAULT_FROM_EMAIL', 'accounts@localhost')

EMAIL_TIMEOUT = int(os.environ.get('DJANGO_EMAIL_TIMEOUT', '10'))
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
proxy_ssl_header = os.environ.get('DJANGO_TRUSTED_PROXY_SSL_HEADER')
if proxy_ssl_header:
    try:
        proxy_header, proxy_value = proxy_ssl_header.split(',', maxsplit=1)
    except ValueError as error:
        raise ImproperlyConfigured(
            'DJANGO_TRUSTED_PROXY_SSL_HEADER must contain header,value.',
        ) from error
    SECURE_PROXY_SSL_HEADER = (proxy_header.strip(), proxy_value.strip())
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_THROTTLE_RATES': {
        # Tight defaults for non-DEBUG; relaxed below when DEBUG is on.
        'auth_signup': '5/hour',
        'auth_login': '10/minute',
        'auth_password_reset_request': '3/hour',
        'auth_password_reset_confirm': '5/hour',
        'auth_organization_options': '60/minute',
    },
}
if DEBUG:
    # LocMem throttle state survives across requests in runserver; keep local DX usable.
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
        'auth_signup': '1000/hour',
        'auth_login': '1000/minute',
        'auth_password_reset_request': '1000/hour',
        'auth_password_reset_confirm': '1000/hour',
        'auth_organization_options': '1000/minute',
    }

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        'CORS_ALLOWED_ORIGINS',
        # Next.js (3000) + legacy Vite (5173) local frontends
        'http://localhost:3000,http://127.0.0.1:3000,'
        'http://localhost:5173,http://127.0.0.1:5173,'
        'http://localhost:8080,http://127.0.0.1:8080',
    ).split(',')
    if origin.strip()
]
if DJANGO_ENV == 'production':
    if not os.environ.get('CORS_ALLOWED_ORIGINS'):
        raise ImproperlyConfigured('CORS_ALLOWED_ORIGINS is required in production.')
    if any(not origin.startswith('https://') for origin in CORS_ALLOWED_ORIGINS):
        raise ImproperlyConfigured('Production CORS origins must use HTTPS.')

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

# Safaricom Daraja (M-Pesa). Secrets come from the environment; never hardcode them.
MPESA_BASE_URL = os.environ.get(
    'MPESA_BASE_URL',
    'https://sandbox.safaricom.co.ke',
).strip().rstrip('/')
if MPESA_BASE_URL and not MPESA_BASE_URL.lower().startswith('https://'):
    raise ImproperlyConfigured('MPESA_BASE_URL must use HTTPS.')
MPESA_CONSUMER_KEY = os.environ.get('MPESA_CONSUMER_KEY', '').strip()
MPESA_CONSUMER_SECRET = os.environ.get('MPESA_CONSUMER_SECRET', '').strip()
MPESA_SHORTCODE = os.environ.get('MPESA_SHORTCODE', '').strip()
MPESA_PASSKEY = os.environ.get('MPESA_PASSKEY', '').strip()
MPESA_CALLBACK_URL = os.environ.get('MPESA_CALLBACK_URL', '').strip()
if MPESA_CALLBACK_URL and not MPESA_CALLBACK_URL.lower().startswith('https://'):
    raise ImproperlyConfigured('MPESA_CALLBACK_URL must use HTTPS.')
MPESA_CALLBACK_AUTH_TOKEN = os.environ.get('MPESA_CALLBACK_AUTH_TOKEN', '').strip()
if DJANGO_ENV == 'production' and len(MPESA_CALLBACK_AUTH_TOKEN) < 32:
    raise ImproperlyConfigured('MPESA_CALLBACK_AUTH_TOKEN must be configured with at least 32 characters in production.')
if DJANGO_ENV == 'production' and (
    not MPESA_CALLBACK_URL or MPESA_CALLBACK_AUTH_TOKEN not in urlsplit(MPESA_CALLBACK_URL).path.split('/')
):
    raise ImproperlyConfigured('MPESA_CALLBACK_URL must include MPESA_CALLBACK_AUTH_TOKEN as a path segment in production.')
try:
    MPESA_TIMEOUT_SECONDS = int(os.environ.get('MPESA_TIMEOUT_SECONDS', '30'))
except ValueError as error:
    raise ImproperlyConfigured('MPESA_TIMEOUT_SECONDS must be an integer.') from error
if MPESA_TIMEOUT_SECONDS <= 0:
    raise ImproperlyConfigured('MPESA_TIMEOUT_SECONDS must be positive.')
MPESA_TRANSACTION_TYPE = os.environ.get(
    'MPESA_TRANSACTION_TYPE',
    'CustomerPayBillOnline',
).strip() or 'CustomerPayBillOnline'
