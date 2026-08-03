from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Load .env but allow skipping via environment variable (used by run_checks to avoid DB overrides)
if not os.getenv('SKIP_LOAD_ENV'):
    load_dotenv(BASE_DIR / '.env', override=False)

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
DEBUG = os.getenv('DEBUG', 'true').lower() == 'true'
ALLOWED_HOSTS = [x.strip() for x in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost,0.0.0.0').split(',') if x.strip()]
# The Next.js container proxies /api and /media to http://backend:8000, so the
# request reaches Django with Host "backend". It must always be allowed
# (in dev and prod), otherwise Django returns 400 DisallowedHost for every call.
for _host in ('backend',):
    if _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)
if DEBUG:
    for host in ['testserver', '172.20.3.94']:
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'accounts',
    'cards',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'config.middleware.LocalCorsMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if DATABASE_URL:
    DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}

LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Asia/Riyadh'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / os.getenv('MEDIA_ROOT', 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000,http://0.0.0.0:3000'
).split(',') if x.strip()]
CORS_ALLOW_ALL_ORIGINS = os.getenv('CORS_ALLOW_ALL_ORIGINS', 'false').lower() == 'true'
# Session auth uses cookies, so credentials must be allowed for the SPA origin.
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000'
).split(',') if x.strip()]

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'auth_login': os.getenv('THROTTLE_LOGIN', '10/min'),
        'auth_register': os.getenv('THROTTLE_REGISTER', '5/min'),
        'auth_forgot': os.getenv('THROTTLE_FORGOT', '5/min'),
        'welcome_test': os.getenv('THROTTLE_WELCOME_TEST', '20/min'),
    },
}

# Authentication / sessions.
# Login accepts either username or email (case-insensitive) + password.
AUTHENTICATION_BACKENDS = [
    'accounts.backends.EmailOrUsernameModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# HTTP is used on the internal LAN by default; flip COOKIE_SECURE to True
# behind an HTTPS reverse proxy or with a local certificate.
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
SESSION_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SAMESITE = os.getenv('CSRF_COOKIE_SAMESITE', 'Lax')
CSRF_COOKIE_SECURE = COOKIE_SECURE
# CSRF cookie must be readable by the SPA so it can echo the token back.
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_AGE = int(os.getenv('SESSION_COOKIE_AGE', str(60 * 60 * 24 * 14)))

# Self-service registration is disabled by default (internal platform).
PUBLIC_REGISTRATION_ENABLED = os.getenv('PUBLIC_REGISTRATION_ENABLED', 'false').lower() == 'true'

# Password-reset links point back to the SPA.
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:3000').rstrip('/')
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', str(60 * 60 * 24)))

# Email: console backend for internal use; swap via EMAIL_BACKEND / SMTP vars.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'false').lower() == 'true'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@business-card-platform.local')

# Welcome emails are ALWAYS sent FROM this single platform address (set in .env).
# The user's profile sender_email is only used as Reply-To.
WELCOME_FROM_EMAIL = os.getenv('WELCOME_FROM_EMAIL', '').strip() or DEFAULT_FROM_EMAIL

# Uploaded card image limits.
MAX_UPLOAD_IMAGE_MB = int(os.getenv('MAX_UPLOAD_IMAGE_MB', '10'))
ALLOWED_IMAGE_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash').strip() or 'gemini-2.5-flash'
ENABLE_WEBSITE_ENRICHMENT = os.getenv('ENABLE_WEBSITE_ENRICHMENT', 'true').lower() == 'true'
ALLOW_GEMINI_WEBSITE_CLASSIFICATION = os.getenv('ALLOW_GEMINI_WEBSITE_CLASSIFICATION', 'false').lower() == 'true'
# How long a cached CompanyDomainEnrichment result is considered fresh.
WEBSITE_ENRICHMENT_TTL_DAYS = int(os.getenv('WEBSITE_ENRICHMENT_TTL_DAYS', '90'))
GEMINI_API_KEYS = [k.strip() for k in os.getenv('GEMINI_API_KEYS', '').split(',') if k.strip()]
if not GEMINI_API_KEYS and GEMINI_API_KEY:
    # Backward compatibility with old single-key deployments.
    GEMINI_API_KEYS = [GEMINI_API_KEY]
GEMINI_KEY_COOLDOWN_SECONDS = int(os.getenv('GEMINI_KEY_COOLDOWN_SECONDS', '60'))
# Daily-quota (RPD) exhaustion cools a key down for much longer than a burst
# rate-limit, so the manager stops retrying an exhausted key and uses others.
GEMINI_KEY_QUOTA_COOLDOWN_SECONDS = int(os.getenv('GEMINI_KEY_QUOTA_COOLDOWN_SECONDS', '900'))
# When ALL keys are momentarily rate-limited, wait up to this many seconds for
# the earliest cooldown to lapse and retry, so a burst self-heals for the user.
GEMINI_ALL_KEYS_WAIT_SECONDS = int(os.getenv('GEMINI_ALL_KEYS_WAIT_SECONDS', '30'))
# NOTE: the old per-card "request budget" (GEMINI_MAX_REQUESTS_PER_CARD) was
# removed — extraction now makes a single Gemini call, so there is no budget to
# exceed. The variable is intentionally no longer read.

# ── Card extraction tuning (central config — do not scatter these numbers) ──
# Card extraction is a structured-extraction task, not open-ended reasoning, so
# we keep temperature at 0, cap the output tokens to the JSON schema size, and
# minimise the thinking budget to reduce cost and latency.
GEMINI_CARD_MODEL = os.getenv('GEMINI_CARD_MODEL', '').strip() or GEMINI_MODEL
# Must comfortably fit the whole JSON schema incl. Arabic raw_text (Arabic is
# token-heavy). Too low → the model hits MAX_TOKENS mid-JSON and extraction
# fails with a generic error. On truncation the extractor auto-retries with a
# larger budget, so this is a floor, not a hard cap.
GEMINI_CARD_MAX_OUTPUT_TOKENS = int(os.getenv('GEMINI_CARD_MAX_OUTPUT_TOKENS', '2048'))
GEMINI_CARD_TEMPERATURE = float(os.getenv('GEMINI_CARD_TEMPERATURE', '0'))
# Thinking budget in tokens. 0 disables thinking for models that support it
# (e.g. gemini-2.5-flash). Set to -1 to let the model decide (dynamic).
GEMINI_CARD_THINKING_BUDGET = int(os.getenv('GEMINI_CARD_THINKING_BUDGET', '0'))
# Bounded retry for transient Gemini errors only (429/5xx/timeout).
GEMINI_CARD_MAX_RETRIES = int(os.getenv('GEMINI_CARD_MAX_RETRIES', '2'))
GEMINI_CARD_RETRY_BASE_DELAY = float(os.getenv('GEMINI_CARD_RETRY_BASE_DELAY', '0.75'))

# Image preprocessing sent to Gemini (the optimised copy, not the archived one).
GEMINI_CARD_IMAGE_MAX_DIMENSION = int(os.getenv('GEMINI_CARD_IMAGE_MAX_DIMENSION', '1800'))
GEMINI_CARD_IMAGE_QUALITY = int(os.getenv('GEMINI_CARD_IMAGE_QUALITY', '82'))
# Hard ceiling for the optimised image sent to Gemini (defensive; the resize
# usually keeps files well under this).
GEMINI_CARD_IMAGE_MAX_BYTES = int(os.getenv('GEMINI_CARD_IMAGE_MAX_BYTES', str(4 * 1024 * 1024)))

# ── Gemini pricing (USD per 1,000,000 tokens) ──────────────────────────────
# Estimation only — the authoritative bill comes from Google. Prices change, so
# keep them here (or override with GEMINI_PRICING_JSON) rather than in code.
# Format: {"model-name": {"input": <usd_per_1M>, "output": <usd_per_1M>}}.
_DEFAULT_GEMINI_PRICING = {
    'gemini-2.5-flash': {'input': '0.30', 'output': '2.50'},
    'gemini-2.5-flash-lite': {'input': '0.10', 'output': '0.40'},
    'gemini-2.5-pro': {'input': '1.25', 'output': '10.00'},
    'gemini-2.0-flash': {'input': '0.10', 'output': '0.40'},
    'gemini-1.5-flash': {'input': '0.075', 'output': '0.30'},
}
try:
    import json as _json

    _override = os.getenv('GEMINI_PRICING_JSON', '').strip()
    GEMINI_PRICING = {**_DEFAULT_GEMINI_PRICING, **(_json.loads(_override) if _override else {})}
except Exception:  # pragma: no cover - defensive: never crash settings on bad JSON
    GEMINI_PRICING = dict(_DEFAULT_GEMINI_PRICING)

APPEND_SLASH = False
