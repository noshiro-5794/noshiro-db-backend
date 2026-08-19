import json
import logging
from io import StringIO
from unittest.mock import patch

import pytest
from django.test import Client, RequestFactory, override_settings

from config.urls import optional_urlpatterns
from shared.http import TrustedProxyMiddleware, get_client_ip
from shared.observability import bind_context
from shared.observability.logging import JsonFormatter


def test_liveness_does_not_check_external_dependencies() -> None:
    response = Client().get("/health/live/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
def test_readiness_checks_database_and_cache() -> None:
    response = Client().get("/health/ready/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_dependency_failure() -> None:
    with patch("config.health.cache.set", side_effect=RuntimeError("unavailable")):
        response = Client().get("/health/ready/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@override_settings(TRUSTED_PROXY_CIDRS=["172.18.0.1/32"])
def test_forwarded_client_ip_is_accepted_only_from_a_trusted_proxy() -> None:
    factory = RequestFactory()
    trusted = factory.get(
        "/",
        REMOTE_ADDR="172.18.0.1",
        HTTP_X_FORWARDED_FOR="203.0.113.10, 172.18.0.1",
    )
    untrusted = factory.get(
        "/",
        REMOTE_ADDR="198.51.100.12",
        HTTP_X_FORWARDED_FOR="203.0.113.10",
    )

    assert get_client_ip(trusted) == "203.0.113.10"
    assert get_client_ip(untrusted) == "198.51.100.12"

    TrustedProxyMiddleware(lambda request: request)(untrusted)
    assert "HTTP_X_FORWARDED_FOR" not in untrusted.META


@override_settings(TRUSTED_PROXY_CIDRS=["172.18.0.0/16"])
def test_client_ip_ignores_spoofed_values_before_the_untrusted_hop() -> None:
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="172.18.0.1",
        HTTP_X_FORWARDED_FOR="192.0.2.7, 203.0.113.10, 172.18.0.2",
    )

    assert get_client_ip(request) == "203.0.113.10"


@override_settings(ENABLE_ADMIN=False, ENABLE_API_DOCS=False)
def test_production_only_routes_are_disabled_by_default() -> None:
    assert optional_urlpatterns() == []


@override_settings(ENABLE_ADMIN=True, ENABLE_API_DOCS=True)
def test_admin_and_interactive_docs_can_be_explicitly_enabled() -> None:
    patterns = optional_urlpatterns()

    assert len(patterns) == 2
    assert any(getattr(pattern, "name", None) == "api-docs" for pattern in patterns)
    assert any(getattr(pattern, "namespace", None) == "admin" for pattern in patterns)


def test_request_context_returns_a_traceable_request_id() -> None:
    response = Client().get("/missing/", HTTP_X_REQUEST_ID="request-123")

    assert response.status_code == 404
    assert response["X-Request-ID"] == "request-123"


def test_json_logging_includes_context_and_redacts_sensitive_extras() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.observability")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with bind_context(request_id="request-123", user_id=42):
        logger.info(
            "example",
            extra={"job_id": "job-123", "access_token": "secret"},
        )

    payload = json.loads(stream.getvalue())
    assert payload["request_id"] == "request-123"
    assert payload["user_id"] == "42"
    assert payload["job_id"] == "job-123"
    assert payload["message"] == "example"
    assert "access_token" not in payload
