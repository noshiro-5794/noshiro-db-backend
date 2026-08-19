from integrations.mcp.django_setup import setup_django

setup_django()

from integrations.mcp import create_internal_mcp_server  # noqa: E402

mcp = create_internal_mcp_server()


if __name__ == "__main__":
    mcp.run(transport="stdio")
