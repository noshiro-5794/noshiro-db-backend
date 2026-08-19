import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema

logger = logging.getLogger(__name__)


def _response(*, status: str, status_code: int = 200) -> JsonResponse:
    response = JsonResponse({"status": status}, status=status_code)
    response["Cache-Control"] = "no-store"
    return response


@require_GET
@never_cache
@extend_schema(exclude=True)
def liveness(request):
    return _response(status="ok")


@require_GET
@never_cache
@extend_schema(exclude=True)
def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        cache_key = "noshiro:health:ready"
        cache.set(cache_key, "ok", timeout=5)
        if cache.get(cache_key) != "ok":
            raise RuntimeError("Cache readiness check failed.")
        cache.delete(cache_key)
    except Exception:
        logger.warning("Readiness dependency check failed", exc_info=True)
        return _response(status="unavailable", status_code=503)
    return _response(status="ok")
