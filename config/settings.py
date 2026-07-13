"""Django settings for the AI Campus OS project."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default="False"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


# --- Core --------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-change-me-in-production"
)
DEBUG = env_bool("DJANGO_DEBUG", "False")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0"
    ).split(",")
    if h.strip()
]
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# Custom user model (auth lives in the accounts app).
AUTH_USER_MODEL = "accounts.User"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # --- Third-party ---
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "channels",
    "django_celery_results",
    "django_celery_beat",
    # --- Local apps (add module apps here as they are built) ---
    "core",
    "accounts",
    "academics",
    "students",
    "faculty",
    "guardians",
    "attendance",
    "assignments",
    "exams",
    "fees",
    "library",
    "hostel",
    "transport",
    "materials",
    "quizzes",
    "placement",
    "notifications",
    "events",
    "complaints",
    "leave",
    "certificates",
    "chat",
    "ai",
    "analytics",
    "dashboards",
    "administration",
    "campus",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # CORS must sit high, right after security, before CommonMiddleware.
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ----------------------------------------------------------------
# Uses Postgres when POSTGRES_DB is set (Docker), otherwise local SQLite.
if os.environ.get("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N / TZ ---------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# --- Static & media files ----------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- File storage: S3 when USE_S3 else local FileSystem ----------------------
USE_S3 = env_bool("USE_S3", "False")
if USE_S3:
    AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
    AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "")
    AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL") or None
    AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN") or None
    AWS_QUERYSTRING_AUTH = env_bool("AWS_QUERYSTRING_AUTH", "True")
    AWS_DEFAULT_ACL = os.environ.get("AWS_DEFAULT_ACL") or None
    default_storage_backend = "storages.backends.s3.S3Boto3Storage"
else:
    default_storage_backend = "django.core.files.storage.FileSystemStorage"

STORAGES = {
    "default": {"BACKEND": default_storage_backend},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis / Cache -----------------------------------------------------------
# Use django-redis when a Redis URL is configured; otherwise fall back to a
# local in-memory cache so `check`/dev work offline with nothing running.
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "aicampus-locmem",
        }
    }

# --- REST Framework ----------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        ["core.renderers.EnvelopeJSONRenderer"]
        + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else [])
    ),
    "EXCEPTION_HANDLER": "core.exceptions.envelope_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_ANON", "1000/min"),
        "user": os.environ.get("THROTTLE_USER", "10000/day"),
        "login": os.environ.get("THROTTLE_LOGIN", "30/min"),
        "password_reset": os.environ.get("THROTTLE_PASSWORD_RESET", "10/min"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# --- SimpleJWT ---------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --- drf-spectacular ---------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "AI Campus OS API",
    "DESCRIPTION": "Multi-role college management platform API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Celery ------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", REDIS_URL or "redis://localhost:6379/0"
)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "django-db")
CELERY_CACHE_BACKEND = "django-cache"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", "False")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# --- Channels ----------------------------------------------------------------
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }

# --- CORS --------------------------------------------------------------------
# The mobile app is a separate origin. Allow-all in dev via env; explicit list otherwise.
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", "False")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = env_bool("CORS_ALLOW_CREDENTIALS", "True")

# --- Security (only enforced when DEBUG is False) ----------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", "True")
    CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", "True")
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
