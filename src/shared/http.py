from ipaddress import ip_address, ip_network

from django.conf import settings


def is_trusted_proxy(value: str | None) -> bool:
    if not value:
        return False
    try:
        remote_ip = ip_address(value)
    except ValueError:
        return False
    return any(
        remote_ip in ip_network(network, strict=False)
        for network in settings.TRUSTED_PROXY_CIDRS
    )


def get_client_ip(request) -> str | None:
    remote_addr = request.META.get("REMOTE_ADDR")
    try:
        remote_ip = ip_address(remote_addr)
    except ValueError:
        return None
    if not is_trusted_proxy(str(remote_ip)):
        return str(remote_ip)

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    forwarded_chain = [value.strip() for value in forwarded_for.split(",") if value]
    if not forwarded_chain or len(forwarded_chain) > 32:
        return str(remote_ip)

    for value in reversed(forwarded_chain):
        try:
            candidate = ip_address(value)
        except ValueError:
            return str(remote_ip)
        if not is_trusted_proxy(str(candidate)):
            return str(candidate)
    return str(remote_ip)


class TrustedProxyMiddleware:
    FORWARDED_HEADERS = (
        "HTTP_FORWARDED",
        "HTTP_X_FORWARDED_FOR",
        "HTTP_X_FORWARDED_HOST",
        "HTTP_X_FORWARDED_PORT",
        "HTTP_X_FORWARDED_PROTO",
        "HTTP_X_REAL_IP",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not is_trusted_proxy(request.META.get("REMOTE_ADDR")):
            for header in self.FORWARDED_HEADERS:
                request.META.pop(header, None)
        request.client_ip = get_client_ip(request)
        return self.get_response(request)
