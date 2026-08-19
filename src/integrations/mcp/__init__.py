def create_external_mcp_server():
    from .external_server import create_external_mcp_server as create

    return create()


def create_internal_mcp_server():
    from .internal_server import create_internal_mcp_server as create

    return create()


__all__ = ["create_external_mcp_server", "create_internal_mcp_server"]
