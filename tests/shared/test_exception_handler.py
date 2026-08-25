from unittest.mock import MagicMock

import pytest
from django.test import override_settings
from rest_framework.exceptions import ValidationError

from shared.api.exception_handler import (
    _get_error_message,
    _problem_response,
    _request_extensions,
    custom_exception_handler,
)
from shared.exceptions import ApplicationError


class TestGetErrorMessage:
    def test_returns_default_for_none(self) -> None:
        assert _get_error_message(None, "default") == "default"

    def test_returns_detail_from_dict(self) -> None:
        assert _get_error_message({"detail": "foo"}) == "foo"

    def test_returns_non_field_error_string(self) -> None:
        assert _get_error_message({"non_field_errors": "bar"}) == "bar"

    def test_returns_first_non_field_error_from_list(self) -> None:
        assert _get_error_message({"non_field_errors": ["first", "second"]}) == "first"

    def test_returns_first_item_from_list(self) -> None:
        assert _get_error_message(["error1", "error2"]) == "error1"

    def test_returns_default_for_empty_list(self) -> None:
        assert _get_error_message([], "default") == "default"

    def test_returns_string_for_other_types(self) -> None:
        assert _get_error_message(42) == "42"


class TestProblemResponse:
    def test_builds_problem_json(self) -> None:
        resp = _problem_response(
            status_code=400,
            detail="Bad input",
            problem_type="about:blank",
        )
        assert resp.status_code == 400
        assert resp["Content-Type"] == "application/problem+json"
        assert resp.data["type"] == "about:blank"
        assert resp.data["detail"] == "Bad input"

    def test_includes_extensions(self) -> None:
        resp = _problem_response(
            status_code=422,
            detail="Unprocessable",
            extensions={"code": "invalid", "instance": "/api/test"},
        )
        assert resp.data["code"] == "invalid"
        assert resp.data["instance"] == "/api/test"


class TestRequestExtensions:
    def test_returns_empty_for_none(self) -> None:
        assert _request_extensions(None) == {}

    def test_includes_instance_path(self) -> None:
        request = MagicMock()
        request.get_full_path.return_value = "/api/v1/test"
        del request.request_id
        result = _request_extensions(request)
        assert result["instance"] == "/api/v1/test"

    def test_includes_trace_id_when_present(self) -> None:
        request = MagicMock()
        request.get_full_path.return_value = "/api/v1/test"
        request.request_id = "req-123"
        result = _request_extensions(request)
        assert result["trace_id"] == "req-123"


class TestCustomExceptionHandler:
    def test_handles_application_error(self) -> None:
        exc = ApplicationError("Not found", status=404, code="not_found")
        context = {"request": None}
        resp = custom_exception_handler(exc, context)
        assert resp.status_code == 404

    def test_handles_validation_error(self) -> None:
        exc = ValidationError({"field": ["required"]})
        context = {"request": None}
        resp = custom_exception_handler(exc, context)
        assert resp.status_code == 400

    @override_settings(DEBUG=True)
    def test_raises_in_debug_for_unhandled(self) -> None:
        exc = RuntimeError("unexpected")
        context = {"request": None, "view": MagicMock(__name__="TestView")}
        with pytest.raises(RuntimeError):
            custom_exception_handler(exc, context)
