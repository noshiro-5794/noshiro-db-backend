from typing import Any

from django.conf import settings


def outbound_proxies() -> dict[str, str] | None:
    proxy_url = getattr(settings, "OUTBOUND_PROXY_URL", "") or ""
    if not proxy_url:
        return None
    return {
        "http://": proxy_url,
        "https://": proxy_url,
    }


def httpx_client_kwargs(**kwargs: Any) -> dict[str, Any]:
    proxies = outbound_proxies()
    if proxies is not None:
        kwargs.setdefault("proxy", proxies["http://"])
    return kwargs
