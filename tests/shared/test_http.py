from unittest.mock import MagicMock

from django.test import override_settings

from shared.http import get_client_ip, is_trusted_proxy


class TestIsTrustedProxy:
    def test_returns_false_for_none(self) -> None:
        assert is_trusted_proxy(None) is False

    def test_returns_false_for_empty_string(self) -> None:
        assert is_trusted_proxy("") is False

    def test_returns_false_for_invalid_ip(self) -> None:
        assert is_trusted_proxy("not-an-ip") is False

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_returns_true_for_trusted_ip(self) -> None:
        assert is_trusted_proxy("10.0.0.1") is True

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_returns_false_for_untrusted_ip(self) -> None:
        assert is_trusted_proxy("192.168.1.1") is False


class TestGetClientIp:
    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_returns_remote_addr_when_not_proxy(self) -> None:
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "192.168.1.1"}
        result = get_client_ip(request)
        assert result == "192.168.1.1"

    def test_returns_none_for_invalid_remote_addr(self) -> None:
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "invalid"}
        result = get_client_ip(request)
        assert result is None

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_uses_x_forwarded_for_when_proxy(self) -> None:
        request = MagicMock()
        request.META = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "203.0.113.1, 10.0.0.2",
        }
        result = get_client_ip(request)
        assert result == "203.0.113.1"

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_falls_back_when_forwarded_chain_invalid(self) -> None:
        request = MagicMock()
        request.META = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "invalid",
        }
        result = get_client_ip(request)
        assert result == "10.0.0.1"

    @override_settings(TRUSTED_PROXY_CIDRS=["10.0.0.0/8"])
    def test_falls_back_when_all_proxies_trusted(self) -> None:
        request = MagicMock()
        request.META = {
            "REMOTE_ADDR": "10.0.0.1",
            "HTTP_X_FORWARDED_FOR": "10.0.0.2, 10.0.0.3",
        }
        result = get_client_ip(request)
        assert result == "10.0.0.1"
