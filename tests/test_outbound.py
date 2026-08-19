from django.test import override_settings

from shared.outbound import httpx_client_kwargs, outbound_proxies


@override_settings(OUTBOUND_PROXY_URL="http://proxy.local:7890")
def test_outbound_proxy_configuration_is_explicit_for_http_clients() -> None:
    assert outbound_proxies() == {
        "http://": "http://proxy.local:7890",
        "https://": "http://proxy.local:7890",
    }

    assert httpx_client_kwargs(timeout=3) == {
        "timeout": 3,
        "proxy": "http://proxy.local:7890",
    }


@override_settings(OUTBOUND_PROXY_URL="")
def test_outbound_proxy_is_optional() -> None:
    assert outbound_proxies() is None
    assert httpx_client_kwargs(timeout=3) == {"timeout": 3}
