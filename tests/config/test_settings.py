from django.conf import settings

from config.settings.base import _normalize_minio_endpoint, _outbound_user_agent


class TestOutboundIdentity:
    def test_provider_user_agents_default_to_the_shared_outbound_identity(
        self,
    ) -> None:
        """A provider User-Agent should only ever come from one place.

        A per-provider override is legitimate, but it has to be an explicit
        environment choice rather than a second default in the source tree.
        """
        for name in (
            "BANGUMI_USER_AGENT",
            "VNDB_USER_AGENT",
            "ANILIST_USER_AGENT",
            "MAL_USER_AGENT",
        ):
            assert getattr(settings, name) == settings.OUTBOUND_USER_AGENT

    def test_outbound_user_agent_combines_name_and_contact(self) -> None:
        assert (
            _outbound_user_agent("acme-db", "ops@example.com")
            == "acme-db (+ops@example.com)"
        )

    def test_outbound_user_agent_degrades_to_the_bare_name_without_contact(
        self,
    ) -> None:
        assert _outbound_user_agent("acme-db", "") == "acme-db"


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
