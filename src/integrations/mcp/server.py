from contextlib import AbstractAsyncContextManager
from typing import Any

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import (
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.auth.provider import TokenVerifier
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Settings
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

Settings.model_rebuild(
    force=True,
    _types_namespace={
        "AbstractAsyncContextManager": AbstractAsyncContextManager,
        "FastMCP": FastMCP,
        "LifespanResultT": Any,
    },
)


class _HTTPRequireAuthMiddleware(RequireAuthMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


class AuthenticatedFastMCP(FastMCP):
    def __init__(
        self,
        *args,
        token_verifier: TokenVerifier,
        required_scopes: list[str],
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._noshiro_token_verifier = token_verifier
        self._noshiro_required_scopes = required_scopes

    def streamable_http_app(self) -> ASGIApp:
        app = super().streamable_http_app()
        protected_app = _HTTPRequireAuthMiddleware(
            app,
            required_scopes=self._noshiro_required_scopes,
        )
        auth_context_app = AuthContextMiddleware(protected_app)
        return AuthenticationMiddleware(
            auth_context_app,
            backend=BearerAuthBackend(self._noshiro_token_verifier),
        )
