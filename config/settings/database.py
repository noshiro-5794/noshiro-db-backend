import os

import dj_database_url

from .base import DEBUG


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


DATABASE_SSL_REQUIRE = _parse_bool(
    os.getenv("DATABASE_SSL_REQUIRE"),
    default=not DEBUG,
)

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=0 if DEBUG else 60,
        conn_health_checks=True,
        ssl_require=DATABASE_SSL_REQUIRE,
    )
}
