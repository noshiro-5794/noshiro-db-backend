import json
from unittest.mock import patch

from django.test import RequestFactory

from config.health import liveness, readiness


class TestLiveness:
    def test_returns_ok(self) -> None:
        request = RequestFactory().get("/health/live/")
        response = liveness(request)
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "ok"


class TestReadiness:
    def test_returns_ok_when_dependencies_healthy(self) -> None:
        request = RequestFactory().get("/health/ready/")
        with (
            patch("config.health.connection"),
            patch("config.health.cache") as mock_cache,
        ):
            mock_cache.get.return_value = "ok"
            response = readiness(request)
            assert response.status_code == 200
            mock_cache.delete.assert_called_once_with("noshiro:health:ready")

    def test_returns_unavailable_when_db_fails(self) -> None:
        request = RequestFactory().get("/health/ready/")
        with patch("config.health.connection") as mock_conn:
            mock_conn.cursor.side_effect = RuntimeError("db down")
            response = readiness(request)
            assert response.status_code == 503
