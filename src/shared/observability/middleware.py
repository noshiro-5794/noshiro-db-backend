import logging
import re
import time
import uuid

from shared.observability.context import bind_context, set_user_id

logger = logging.getLogger("noshiro.request")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied_request_id = request.headers.get("X-Request-ID", "")
        request_id = (
            supplied_request_id
            if _REQUEST_ID.fullmatch(supplied_request_id)
            else uuid.uuid4().hex
        )
        request.request_id = request_id
        started_at = time.monotonic()

        with bind_context(request_id=request_id):
            response = self.get_response(request)
            user = getattr(request, "user", None)
            if getattr(user, "is_authenticated", False):
                set_user_id(user.pk)
            response["X-Request-ID"] = request_id
            if request.path not in {"/health/live/", "/health/ready/"}:
                logger.info(
                    "HTTP request completed",
                    extra={
                        "duration_ms": round(
                            (time.monotonic() - started_at) * 1000,
                            2,
                        ),
                        "client_ip": getattr(request, "client_ip", None),
                        "http_method": request.method,
                        "http_path": request.path,
                        "status_code": response.status_code,
                    },
                )
            return response
