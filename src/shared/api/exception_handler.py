import logging
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler

from shared.api.responses import APIResponse
from shared.errors import ApplicationError

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
) -> APIResponse:
    if isinstance(exc, ApplicationError):
        return APIResponse(
            code=exc.code,
            message=exc.message,
            data=None,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    response = exception_handler(exc, context)

    if isinstance(exc, ValidationError):
        return APIResponse(
            code=40000,
            message="validation error",
            data=response.data if response is not None else None,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if response is not None:
        return APIResponse(
            code=response.status_code * 100,
            message=_get_error_message(response.data),
            data=response.data,
            status_code=response.status_code,
        )

    if settings.DEBUG:
        raise exc

    logger.error(
        "Unhandled API exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"view": type(context.get("view")).__name__},
    )
    return APIResponse(
        code=50000,
        message="internal error",
        data=None,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
