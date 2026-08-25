import os
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

from .environment import load_local_environment

load_local_environment()

test_database_url = os.environ.get("TEST_DATABASE_URL")
if not test_database_url:
    raise ImproperlyConfigured(
        "TEST_DATABASE_URL must point to a dedicated PostgreSQL test database."
    )

parsed_test_database_url = urlparse(test_database_url)
test_database_name = unquote(parsed_test_database_url.path.lstrip("/"))
if parsed_test_database_url.scheme not in {"postgres", "postgresql"}:
    raise ImproperlyConfigured("TEST_DATABASE_URL must use PostgreSQL.")
if not test_database_name.endswith("_test"):
    raise ImproperlyConfigured("TEST_DATABASE_URL database name must end with '_test'.")

test_environment = {
    "CELERY_BROKER_URL": "memory://",
    "CELERY_RESULT_BACKEND": "cache+memory://",
    "CORS_ALLOW_ALL_ORIGINS": "False",
    "DATABASE_SSL_REQUIRE": "False",
    "DATABASE_URL": test_database_url,
    "DJANGO_ALLOWED_HOSTS": "testserver,localhost",
    "DJANGO_SECRET_KEY": "test-only-secret-key-with-at-least-32-bytes",
    "FRONTEND_SITE_URL": "https://app.noshiro.moe",
    "MINIO_ACCESS_KEY": "test",
    "MINIO_BUCKET": "test",
    "MINIO_ENDPOINT": "127.0.0.1:9000",
    "MINIO_PUBLIC_URL": "http://127.0.0.1:9000",
    "MINIO_SECRET_KEY": "test",
    "OUTBOUND_PROXY_URL": "",
    "PROBLEM_BASE_URI": "https://app.noshiro.moe/problems/",
}

os.environ.update(test_environment)

from .base import *  # noqa: E402

DEBUG = False

ALLOWED_HOSTS = ["testserver", "localhost"]

DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
DATABASES["default"]["TEST"] = {"NAME": test_database_name}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True

CELERY_TASK_EAGER_PROPAGATES = True
