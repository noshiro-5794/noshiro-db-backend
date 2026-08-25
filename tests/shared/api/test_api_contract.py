from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.index.exceptions import SubjectNotFound
from shared.api.exception_handler import custom_exception_handler
from shared.api.pagination import DefaultPageNumberPagination, TimelineCursorPagination
from shared.exceptions import ApplicationError


class ExampleApplicationError(ApplicationError):
    default_code = "example.application_error"
    default_message = "example error"


def test_application_error_is_framework_independent() -> None:
    error = ExampleApplicationError(message="custom error", code="example.custom")

    assert str(error) == "custom error"
    assert error.message == "custom error"
    assert error.code == "example.custom"
    assert not isinstance(error, APIException)


@override_settings(PROBLEM_BASE_URI="https://app.noshiro.moe/problems/")
def test_application_error_uses_its_public_code_and_message() -> None:
    response = custom_exception_handler(ExampleApplicationError(), {})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {
        "type": f"{settings.PROBLEM_BASE_URI.rstrip('/')}/example.application_error",
        "title": "Bad Request",
        "status": 400,
        "detail": "example error",
        "code": "example.application_error",
    }
    assert response["Content-Type"] == "application/problem+json"


@override_settings(PROBLEM_BASE_URI="https://app.noshiro.moe/problems/")
def test_domain_error_controls_problem_status_and_type() -> None:
    response = custom_exception_handler(SubjectNotFound(), {})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["type"] == (
        f"{settings.PROBLEM_BASE_URI.rstrip('/')}/index.subject_not_found"
    )
    assert response.data["code"] == "index.subject_not_found"


def test_problem_response_links_request_instance_and_trace_id() -> None:
    request = Request(APIRequestFactory().get("/api/v1/example/?page=2"))
    request.request_id = "request-123"

    response = custom_exception_handler(
        ExampleApplicationError(),
        {"request": request},
    )

    assert response.data["instance"] == "/api/v1/example/?page=2"
    assert response.data["trace_id"] == "request-123"


def test_validation_error_preserves_field_details() -> None:
    response = custom_exception_handler(
        ValidationError({"title": ["This field is required."]}),
        {},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {
        "type": "about:blank",
        "title": "Bad Request",
        "status": 400,
        "detail": "Request validation failed.",
        "errors": {"title": ["This field is required."]},
    }
    assert response["Content-Type"] == "application/problem+json"


@override_settings(DEBUG=False)
@override_settings(PROBLEM_BASE_URI="https://app.noshiro.moe/problems/")
def test_unhandled_exception_uses_the_safe_public_response() -> None:
    response = custom_exception_handler(RuntimeError("private detail"), {})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data == {
        "type": f"{settings.PROBLEM_BASE_URI.rstrip('/')}/internal-server-error",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "An unexpected error occurred.",
    }
    assert response["Content-Type"] == "application/problem+json"


def test_pagination_returns_a_collection_resource() -> None:
    request = Request(APIRequestFactory().get("/items/", {"page": 2, "page_size": 3}))
    pagination = DefaultPageNumberPagination()

    page = pagination.paginate_queryset(list(range(8)), request)
    response = pagination.get_paginated_response(page)

    assert response.data["count"] == 8
    assert response.data["results"] == [3, 4, 5]
    assert response.data["next"] is not None
    assert response.data["previous"] is not None


def test_cursor_pagination_returns_a_stable_timeline_resource() -> None:
    pagination = TimelineCursorPagination()
    pagination.has_next = False
    pagination.has_previous = False

    assert pagination.ordering == ("-created_at", "-id")
    assert pagination.page_size == 16
    assert pagination.page_size_query_param == "page_size"
    assert pagination.max_page_size == 64
    assert set(pagination.get_paginated_response([]).data) == {
        "next",
        "previous",
        "results",
    }
