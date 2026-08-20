import logging
from http import HTTPStatus
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from shared.exceptions import ApplicationError, problem_type_uri

logger = logging.getLogger(__name__)


def _get_error_message(data: Any, default: str = "request failed") -> str:
    if data is None:
        return default

    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return str(detail)

        non_field_errors = data.get("non_field_errors")
        if non_field_errors:
            if isinstance(non_field_errors, list):
                return str(non_field_errors[0])
            return str(non_field_errors)

        return default

    if isinstance(data, list):
        return str(data[0]) if data else default

    return str(data)


def custom_exception_handler(
    exc: Exception,
    context: dict[str, Any],
) -> Response:
    request = context.get("request")
    request_extensions = _request_extensions(request)
    if isinstance(exc, ApplicationError):
        return _problem_response(
            status_code=exc.status,
            detail=exc.message,
            extensions={"code": exc.code, **request_extensions},
            problem_type=exc.problem_type,
        )

    response = exception_handler(exc, context)
    if response is not None:
        detail = _get_error_message(
            response.data, HTTPStatus(response.status_code).phrase
        )
        extensions = None
        if isinstance(exc, ValidationError):
            detail = "Request validation failed."
            extensions = {"errors": response.data}
        if request_extensions:
            extensions = {**(extensions or {}), **request_extensions}
        return _problem_response(
            status_code=response.status_code,
            detail=detail,
            extensions=extensions,
            headers=response.headers,
            problem_type="about:blank",
        )

    if settings.DEBUG:
        raise exc

    logger.error(
        "Unhandled API exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"view": type(context.get("view")).__name__},
    )
    return _problem_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected error occurred.",
        extensions=request_extensions,
        problem_type=problem_type_uri("internal-server-error"),
    )


def _request_extensions(request) -> dict[str, str]:
    if request is None:
        return {}
    extensions = {"instance": request.get_full_path()}
    if request_id := getattr(request, "request_id", None):
        extensions["trace_id"] = request_id
    return extensions


def _problem_response(
    *,
    status_code: int,
    detail: str,
    extensions: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    problem_type: str = "about:blank",
) -> Response:
    body = {
        "type": problem_type,
        "title": HTTPStatus(status_code).phrase,
        "status": status_code,
        "detail": detail,
        **(extensions or {}),
    }
    response = Response(
        body,
        status=status_code,
        headers=headers,
        content_type="application/problem+json",
    )
    response["Content-Type"] = "application/problem+json"
    return response
