from .environment import load_local_environment

load_local_environment()

from .base import *  # noqa: E402

DEBUG = True

DATABASES["default"]["CONN_MAX_AGE"] = 0

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
]

CORS_ALLOW_ALL_ORIGINS = True
