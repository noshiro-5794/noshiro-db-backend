from datetime import timedelta
from urllib.parse import urlparse

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

from .environment import BASE_DIR as BASE_DIR
from .environment import env, env_list

# Core

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-secret-key")

DEBUG = False

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

DEPLOYMENT_TIME_ZONE = env("TZ", default="Asia/Shanghai")

USE_I18N = True

USE_TZ = True

# Applications

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "django_filters",
    "drf_spectacular",
    "rest_framework",
    "corsheaders",
    "rest_framework_simplejwt.token_blacklist",
]

LOCAL_APPS = [
    "apps.ai",
    "apps.users",
    "apps.community",
    "apps.index",
    "apps.sync",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Request handling

MIDDLEWARE = [
    "shared.http.TrustedProxyMiddleware",
    "shared.observability.middleware.RequestContextMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

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

# Database

DATABASE_SSL_REQUIRE = env.bool("DATABASE_SSL_REQUIRE", default=True)

_database = env.db("DATABASE_URL")
if not _database["ENGINE"].startswith("django.db.backends.postgresql"):
    raise ImproperlyConfigured("DATABASE_URL must use PostgreSQL.")
_database["CONN_MAX_AGE"] = 60
_database["CONN_HEALTH_CHECKS"] = True

if DATABASE_SSL_REQUIRE and _database["ENGINE"].startswith(
    "django.db.backends.postgresql"
):
    _database.setdefault("OPTIONS", {}).setdefault("sslmode", "require")

DATABASES = {"default": _database}

# Cache

CACHES = {
    "default": env.cache_url("CACHE_URL", default="locmemcache://"),
}

# Authentication and API

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "shared.api.authentication.ContextJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": "10/min",
        "auth_refresh": "30/min",
        "auth_register": "5/hour",
        "auth_reset": "5/hour",
        "verification": "5/min",
    },
    "EXCEPTION_HANDLER": "shared.api.exception_handler.custom_exception_handler",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_SCHEMA_CLASS": "shared.api.schema.NoshiroAutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Noshiro DB API",
    "DESCRIPTION": "Source-neutral anime and galgame knowledge API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "EntityLifecycle": "apps.index.models.Entity.Lifecycle",
        "EntityAudience": "apps.index.models.Entity.Audience",
        "EntityKind": "apps.index.models.Entity.Kind",
        "LibraryStatus": "apps.users.models.UserSubject.Status",
        "ReleaseStatus": "apps.users.models.UserRelease.Status",
        "SyncJobStatus": "apps.sync.models.SyncJob.Status",
        "CommunityReportStatus": "apps.community.models.CommunityReport.ReportStatus",
    },
}

SPECTACULAR_EXTENSIONS = ("shared.api.schema.ContextJWTScheme",)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=2),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "CHECK_REVOKE_TOKEN": True,
}

JWT_REFRESH_COOKIE_NAME = env("JWT_REFRESH_COOKIE_NAME", default="noshiro_refresh")
JWT_REFRESH_COOKIE_PATH = env("JWT_REFRESH_COOKIE_PATH", default="/api/v1/auth/")
JWT_REFRESH_COOKIE_DOMAIN = env("JWT_REFRESH_COOKIE_DOMAIN", default=None) or None
JWT_REFRESH_COOKIE_SECURE = env.bool("JWT_REFRESH_COOKIE_SECURE", default=False)
JWT_REFRESH_COOKIE_HTTP_ONLY = True
JWT_REFRESH_COOKIE_SAMESITE = env("JWT_REFRESH_COOKIE_SAMESITE", default="Lax")
JWT_REFRESH_COOKIE_MAX_AGE = env.int(
    "JWT_REFRESH_COOKIE_MAX_AGE", default=30 * 24 * 60 * 60
)

# Browser security

CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=False)

CORS_ALLOW_CREDENTIALS = env.bool("CORS_ALLOW_CREDENTIALS", default=False)

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

TRUSTED_PROXY_CIDRS = env_list("TRUSTED_PROXY_CIDRS")

ENABLE_ADMIN = True

ENABLE_API_DOCS = True

LOG_LEVEL = env("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "shared.observability.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django.server": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# Celery

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=None)

CELERY_RESULT_BACKEND = None

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": env.int("CELERY_VISIBILITY_TIMEOUT", default=7200),
}

CELERY_ACCEPT_CONTENT = ["json"]

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = DEPLOYMENT_TIME_ZONE

CELERY_TASK_TIME_LIMIT = 30

CELERY_TASK_SOFT_TIME_LIMIT = 20

CELERY_TASK_ACKS_LATE = True

CELERY_WORKER_PREFETCH_MULTIPLIER = 1

CELERY_TASK_DEFAULT_RETRY_DELAY = 60

CELERY_TASK_MAX_RETRIES = 3

CELERY_TASK_DEFAULT_QUEUE = "realtime"

CELERY_TASK_QUEUES = {
    "realtime": {
        "exchange": "realtime",
        "routing_key": "realtime",
    },
    "ai": {
        "exchange": "ai",
        "routing_key": "ai",
    },
    "sync": {
        "exchange": "sync",
        "routing_key": "sync",
    },
}

CELERY_TASK_ROUTES = {
    "apps.users.tasks.email_tasks.send_verification_email": {"queue": "realtime"},
    "apps.sync.tasks.maintenance.*": {"queue": "realtime"},
    "apps.ai.tasks.*": {"queue": "ai"},
    "apps.sync.tasks.*": {"queue": "sync"},
}

CELERY_BEAT_SCHEDULE = {
    "daily-calendar-sync": {
        "task": "apps.sync.tasks.calendar.sync_calendar_task",
        "schedule": crontab(
            hour=env.int("SYNC_CALENDAR_CRON_HOUR", default=3),
            minute=env.int("SYNC_CALENDAR_CRON_MINUTE", default=30),
        ),
    },
    "daily-incremental-sync": {
        "task": "apps.sync.tasks.incremental.run_incremental_sync_task",
        "schedule": crontab(
            hour=env.int("SYNC_INCREMENTAL_CRON_HOUR", default=4),
            minute=env.int("SYNC_INCREMENTAL_CRON_MINUTE", default=0),
        ),
    },
    "worker-heartbeat": {
        "task": "apps.sync.tasks.maintenance.worker_heartbeat",
        "schedule": 60.0,
    },
    "stale-sync-job-scan": {
        "task": "apps.sync.tasks.maintenance.scan_stale_sync_jobs",
        "schedule": 300.0,
    },
}

# Email and external services

RESEND_API_KEY = env("RESEND_API_KEY", default=None)

EMAIL_FROM = env("EMAIL_FROM", default="noreply@noshiro.moe")

FRONTEND_SITE_URL = env("FRONTEND_SITE_URL", default="https://app.noshiro.moe")

PROBLEM_BASE_URI = env(
    "PROBLEM_BASE_URI",
    default=f"{FRONTEND_SITE_URL.rstrip('/')}/problems/",
)

BANGUMI_API_BASE_URL = env(
    "BANGUMI_API_BASE_URL",
    default="https://api.bgm.tv",
)

BANGUMI_API_KEY = env("BANGUMI_API_KEY", default=None)

BANGUMI_USER_AGENT = env(
    "BANGUMI_USER_AGENT",
    default="Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)",
)

BANGUMI_TIMEOUT = env.float("BANGUMI_TIMEOUT", default=30)

BANGUMI_RATE_LIMIT_INTERVAL = env.float(
    "BANGUMI_RATE_LIMIT_INTERVAL",
    default=0.3,
)
BANGUMI_IMAGE_ALLOWED_HOSTS = env_list(
    "BANGUMI_IMAGE_ALLOWED_HOSTS",
    default=("lain.bgm.tv",),
)

BANGUMI_IMAGE_MAX_BYTES = env.int(
    "BANGUMI_IMAGE_MAX_BYTES",
    default=10 * 1024 * 1024,
)

VNDB_API_BASE_URL = env(
    "VNDB_API_BASE_URL",
    default="https://api.vndb.org/kana",
)
VNDB_USER_AGENT = env(
    "VNDB_USER_AGENT",
    default="Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)",
)
VNDB_TIMEOUT = env.float("VNDB_TIMEOUT", default=30)
VNDB_RATE_LIMIT_INTERVAL = env.float(
    "VNDB_RATE_LIMIT_INTERVAL",
    default=1.0,
)

ANILIST_API_BASE_URL = env(
    "ANILIST_API_BASE_URL",
    default="https://graphql.anilist.co",
)
ANILIST_USER_AGENT = env(
    "ANILIST_USER_AGENT",
    default="Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)",
)
ANILIST_TIMEOUT = env.float("ANILIST_TIMEOUT", default=30)
ANILIST_RATE_LIMIT_INTERVAL = env.float(
    "ANILIST_RATE_LIMIT_INTERVAL",
    default=0.75,
)

AI_AGENT_API_BASE_URL = env(
    "AI_AGENT_API_BASE_URL",
    default="https://api.siliconflow.cn/v1/chat/completions",
)

AI_AGENT_API_KEY = env("AI_AGENT_API_KEY", default=None)


AI_PRIMARY_MODEL = env(
    "AI_PRIMARY_MODEL",
    default="zai-org/GLM-5.2",
)

AI_FAST_MODEL = env(
    "AI_FAST_MODEL",
    default="deepseek-ai/DeepSeek-V4-Flash-0731",
)

AI_REASONING_MODEL = env(
    "AI_REASONING_MODEL",
    default="deepseek-ai/DeepSeek-V4-Pro",
)

AI_EMBEDDING_MODEL = env(
    "AI_EMBEDDING_MODEL",
    default="Qwen/Qwen3-Embedding-8B",
)

AI_AGENT_TIMEOUT = env.float("AI_AGENT_TIMEOUT", default=30)

# Web evidence for AI enrichment. WEB_SEARCH_PROVIDER is one of "tavily",
# "none"; without a key the harness degrades to model-only evidence.
WEB_SEARCH_PROVIDER = env("WEB_SEARCH_PROVIDER", default="none")
WEB_SEARCH_API_KEY = env("WEB_SEARCH_API_KEY", default=None)
WEB_SEARCH_BASE_URL = env(
    "WEB_SEARCH_BASE_URL",
    default="https://api.tavily.com",
)
WEB_SEARCH_TIMEOUT = env.float("WEB_SEARCH_TIMEOUT", default=20)
WEB_SEARCH_CACHE_DAYS = env.int("WEB_SEARCH_CACHE_DAYS", default=30)
WEB_FETCH_TIMEOUT = env.float("WEB_FETCH_TIMEOUT", default=20)
WEB_FETCH_MAX_BYTES = env.int("WEB_FETCH_MAX_BYTES", default=65536)

# Bounded AI enrichment policy. Enrichment never runs on the full catalog; the
# sample cap and batch size bound per-campaign spend. Auto-apply is off by
# default: results are persisted as reviewable AIClaim evidence first.
AI_ENRICH_MIN_CONFIDENCE = env.float("AI_ENRICH_MIN_CONFIDENCE", default=0.85)
AI_ENRICH_SAMPLE_SIZE = env.int("AI_ENRICH_SAMPLE_SIZE", default=200)
AI_ENRICH_APPLY = env.bool("AI_ENRICH_APPLY", default=False)
AI_ENRICH_LANGUAGES = env_list("AI_ENRICH_LANGUAGES", default=("zh", "ja", "en"))

OUTBOUND_PROXY_URL = env("OUTBOUND_PROXY_URL", default=None)

OUTBOUND_NO_PROXY_HOSTS = env_list("OUTBOUND_NO_PROXY_HOSTS")

MCP_HOST = env("MCP_HOST", default="127.0.0.1")
MCP_PORT = env.int("MCP_PORT", default=8010)
MCP_RATE_LIMIT = env.int("MCP_RATE_LIMIT", default=60)
MCP_RATE_WINDOW_SECONDS = env.int("MCP_RATE_WINDOW_SECONDS", default=60)

HCAPTCHA_ENABLED = env.bool("HCAPTCHA_ENABLED", default=False)

HCAPTCHA_SECRET_KEY = env("HCAPTCHA_SECRET_KEY", default="")

HCAPTCHA_SITEVERIFY_URL = env(
    "HCAPTCHA_SITEVERIFY_URL",
    default="https://api.hcaptcha.com/siteverify",
)

HCAPTCHA_TIMEOUT = env.float("HCAPTCHA_TIMEOUT", default=5)

# Synchronization

SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE = env.int(
    "SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE", default=1000
)

SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS = env.int(
    "SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS", default=20
)

SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS = env.int(
    "SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS", default=50
)

# Object storage and uploads


def _normalize_minio_endpoint(value: str | None) -> tuple[str | None, bool | None]:
    if not value:
        return None, None

    endpoint = value.strip().rstrip("/")
    parsed = urlparse(endpoint)

    if parsed.scheme in {"http", "https"}:
        return parsed.netloc, parsed.scheme == "https"

    return endpoint, None


MINIO_ENDPOINT_RAW = env("MINIO_ENDPOINT", default=None)

MINIO_ENDPOINT, MINIO_ENDPOINT_USES_HTTPS = _normalize_minio_endpoint(
    MINIO_ENDPOINT_RAW
)

MINIO_ACCESS_KEY = env("MINIO_ACCESS_KEY", default=None)

MINIO_SECRET_KEY = env("MINIO_SECRET_KEY", default=None)

MINIO_USE_HTTPS = (
    MINIO_ENDPOINT_USES_HTTPS
    if MINIO_ENDPOINT_USES_HTTPS is not None
    else env.bool("MINIO_USE_HTTPS", default=False)
)

MINIO_BUCKET = env("MINIO_BUCKET", default=None)

MINIO_PUBLIC_URL = env("MINIO_PUBLIC_URL", default=None) or (
    f"{'https' if MINIO_USE_HTTPS else 'http'}://{MINIO_ENDPOINT}"
    if MINIO_ENDPOINT
    else None
)

AVATAR_MAX_UPLOAD_SIZE = env.int("AVATAR_MAX_UPLOAD_SIZE", default=10 * 1024 * 1024)

AVATAR_ALLOWED_CONTENT_TYPES = [
    content_type.lower()
    for content_type in env_list(
        "AVATAR_ALLOWED_CONTENT_TYPES",
        default=("image/jpeg", "image/png", "image/webp"),
    )
]

# Static and media files

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"
