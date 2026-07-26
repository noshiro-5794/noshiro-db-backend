from collections.abc import Mapping
from typing import Any

from rest_framework import status
from rest_framework.response import Response


class APIResponse(Response):
    def __init__(
        self,
        *,
        code: int = 0,
        message: str = "",
        data: Any = None,
        status_code: int = status.HTTP_200_OK,
        headers: Mapping[str, str] | None = None,
        exception: bool = False,
        content_type: str | None = None,
    ) -> None:
        response_data = {"code": code, "message": message, "data": data}
        super().__init__(
            data=response_data,
            status=status_code,
            headers=headers,
            exception=exception,
            content_type=content_type,
        )


def success_response(
    *, data: Any = None, message: str = "", status_code: int = status.HTTP_200_OK
) -> APIResponse:
    return APIResponse(code=0, message=message, data=data, status_code=status_code)
