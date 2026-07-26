from django.test import override_settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from shared.api.exception_handler import custom_exception_handler
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response
from shared.errors import ApplicationError


class ExampleApplicationError(ApplicationError):
    default_code = 12345
    default_message = "example error"


def test_success_response_uses_the_public_envelope() -> None:
    response = success_response(
        data={"id": 1},
        message="created",
        status_code=status.HTTP_201_CREATED,
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data == {
        "code": 0,
        "message": "created",
        "data": {"id": 1},
    }


def test_application_error_is_framework_independent() -> None:
    error = ExampleApplicationError(message="custom error", code=54321)

    assert str(error) == "custom error"
    assert error.message == "custom error"
    assert error.code == 54321
    assert not isinstance(error, APIException)


def test_application_error_uses_its_public_code_and_message() -> None:
    response = custom_exception_handler(ExampleApplicationError(), {})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {
        "code": 12345,
        "message": "example error",
        "data": None,
    }


def test_validation_error_preserves_field_details() -> None:
    response = custom_exception_handler(
        ValidationError({"title": ["This field is required."]}),
        {},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == 40000
    assert response.data["message"] == "validation error"
    assert response.data["data"] == {"title": ["This field is required."]}


@override_settings(DEBUG=False)
def test_unhandled_exception_uses_the_safe_public_response() -> None:
    response = custom_exception_handler(RuntimeError("private detail"), {})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data == {
        "code": 50000,
        "message": "internal error",
        "data": None,
    }


def test_pagination_data_stays_inside_the_public_envelope() -> None:
    request = Request(APIRequestFactory().get("/items/", {"page": 2, "page_size": 3}))
    pagination = DefaultPageNumberPagination()

    page = pagination.paginate_queryset(list(range(8)), request)
    response = pagination.get_paginated_response(page)

    assert response.data["code"] == 0
    assert response.data["message"] == ""
    assert response.data["data"]["count"] == 8
    assert response.data["data"]["results"] == [3, 4, 5]
    assert response.data["data"]["next"] is not None
    assert response.data["data"]["previous"] is not None
