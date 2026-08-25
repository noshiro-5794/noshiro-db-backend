from config.settings.base import _normalize_minio_endpoint


class TestNormalizeMinioEndpoint:
    def test_returns_none_for_none(self) -> None:
        assert _normalize_minio_endpoint(None) == (None, None)

    def test_returns_none_for_empty(self) -> None:
        assert _normalize_minio_endpoint("") == (None, None)

    def test_parses_https_url(self) -> None:
        netloc, uses_https = _normalize_minio_endpoint("https://minio.example.com")
        assert netloc == "minio.example.com"
        assert uses_https is True

    def test_parses_http_url(self) -> None:
        netloc, uses_https = _normalize_minio_endpoint("http://minio.example.com")
        assert netloc == "minio.example.com"
        assert uses_https is False

    def test_returns_raw_endpoint_for_no_scheme(self) -> None:
        endpoint, uses_https = _normalize_minio_endpoint("minio:9000")
        assert endpoint == "minio:9000"
        assert uses_https is None
