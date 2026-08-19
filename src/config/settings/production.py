from ipaddress import ip_network
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if not SECRET_KEY or SECRET_KEY == "unsafe-secret-key":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

if CORS_ALLOW_ALL_ORIGINS:
    raise ImproperlyConfigured("CORS_ALLOW_ALL_ORIGINS must be False in production.")

required_settings = {
    "CACHE_URL": CACHES["default"]["BACKEND"]
    == "django.core.cache.backends.redis.RedisCache",
    "CELERY_BROKER_URL": bool(CELERY_BROKER_URL),
    "RESEND_API_KEY": bool(RESEND_API_KEY),
    "MINIO_ENDPOINT": bool(MINIO_ENDPOINT),
    "MINIO_ACCESS_KEY": bool(MINIO_ACCESS_KEY),
    "MINIO_SECRET_KEY": bool(MINIO_SECRET_KEY),
    "MINIO_BUCKET": bool(MINIO_BUCKET),
    "MINIO_PUBLIC_URL": bool(MINIO_PUBLIC_URL),
}
missing_settings = [
    name for name, is_configured in required_settings.items() if not is_configured
]
if missing_settings:
    raise ImproperlyConfigured(
        "Missing required production settings: " + ", ".join(missing_settings)
    )

if HCAPTCHA_ENABLED and not HCAPTCHA_SECRET_KEY:
    raise ImproperlyConfigured(
        "HCAPTCHA_SECRET_KEY must be set when HCAPTCHA_ENABLED is True."
    )

if not JWT_REFRESH_COOKIE_SECURE:
    raise ImproperlyConfigured("JWT_REFRESH_COOKIE_SECURE must be True in production.")

if JWT_REFRESH_COOKIE_SAMESITE not in {"Lax", "Strict", "None"}:
    raise ImproperlyConfigured(
        "JWT_REFRESH_COOKIE_SAMESITE must be Lax, Strict, or None."
    )

positive_settings = {
    "BANGUMI_TIMEOUT": BANGUMI_TIMEOUT,
    "BANGUMI_IMAGE_MAX_BYTES": BANGUMI_IMAGE_MAX_BYTES,
    "AI_AGENT_TIMEOUT": AI_AGENT_TIMEOUT,
    "MCP_PORT": MCP_PORT,
    "MCP_RATE_LIMIT": MCP_RATE_LIMIT,
    "MCP_RATE_WINDOW_SECONDS": MCP_RATE_WINDOW_SECONDS,
    "HCAPTCHA_TIMEOUT": HCAPTCHA_TIMEOUT,
    "SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE": SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE,
    "SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS": SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS,
    "SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS": SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS,
    "AVATAR_MAX_UPLOAD_SIZE": AVATAR_MAX_UPLOAD_SIZE,
    "JWT_REFRESH_COOKIE_MAX_AGE": JWT_REFRESH_COOKIE_MAX_AGE,
}
invalid_positive_settings = [
    name for name, value in positive_settings.items() if value <= 0
]
if invalid_positive_settings:
    raise ImproperlyConfigured(
        "Production settings must be positive: " + ", ".join(invalid_positive_settings)
    )

if BANGUMI_RATE_LIMIT_INTERVAL < 0:
    raise ImproperlyConfigured(
        "BANGUMI_RATE_LIMIT_INTERVAL must be greater than or equal to zero."
    )

if not BANGUMI_IMAGE_ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "BANGUMI_IMAGE_ALLOWED_HOSTS must contain at least one host."
    )

if not TRUSTED_PROXY_CIDRS:
    raise ImproperlyConfigured(
        "TRUSTED_PROXY_CIDRS must list the reverse proxy addresses in production."
    )
try:
    for trusted_proxy_cidr in TRUSTED_PROXY_CIDRS:
        ip_network(trusted_proxy_cidr, strict=False)
except ValueError as exc:
    raise ImproperlyConfigured(
        "TRUSTED_PROXY_CIDRS must contain valid IPv4 or IPv6 networks."
    ) from exc

https_url_settings = {
    "FRONTEND_SITE_URL": FRONTEND_SITE_URL,
    "MINIO_PUBLIC_URL": MINIO_PUBLIC_URL,
}
invalid_https_settings = [
    name
    for name, value in https_url_settings.items()
    if urlparse(value).scheme != "https"
]
if invalid_https_settings:
    raise ImproperlyConfigured(
        "Production public URLs must use HTTPS: " + ", ".join(invalid_https_settings)
    )

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/"]

SECURE_CONTENT_TYPE_NOSNIFF = True

X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True

SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_SECURE = True

CSRF_COOKIE_HTTPONLY = False

SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30

SECURE_HSTS_INCLUDE_SUBDOMAINS = True

SECURE_HSTS_PRELOAD = True

ENABLE_ADMIN = env.bool("ENABLE_ADMIN", default=False)

ENABLE_API_DOCS = env.bool("ENABLE_API_DOCS", default=False)

SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)

if not 0 <= SENTRY_TRACES_SAMPLE_RATE <= 1:
    raise ImproperlyConfigured("SENTRY_TRACES_SAMPLE_RATE must be between 0 and 1.")

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )
