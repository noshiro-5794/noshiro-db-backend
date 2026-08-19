import time

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.core.exceptions import ValidationError
from mcp.server.auth.provider import AccessToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class NoshiroJWTTokenVerifier:
    SCOPES = ["knowledge:read"]

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            validated = JWTAuthentication().get_validated_token(token)
        except (InvalidToken, TokenError):
            return None
        token_type = validated.get("token_type")
        user_id = validated.get("user_id")
        expires_at = validated.get("exp")
        if token_type != "access" or user_id is None or expires_at is None:
            return None
        normalized_user_id = await self._active_user_id(user_id)
        if normalized_user_id is None:
            return None
        return AccessToken(
            token=token,
            client_id=f"noshiro-user-{normalized_user_id}",
            scopes=self.SCOPES,
            expires_at=int(expires_at),
            subject=normalized_user_id,
            claims={"token_type": token_type},
        )

    @staticmethod
    @sync_to_async(thread_sensitive=True)
    def _active_user_id(user_id) -> str | None:
        from apps.users.models import User

        try:
            normalized_user_id = User._meta.pk.to_python(user_id)
        except (TypeError, ValueError, ValidationError):
            return None
        if normalized_user_id is None:
            return None
        if not User.objects.filter(pk=normalized_user_id, is_active=True).exists():
            return None
        return str(normalized_user_id)


class MCPRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds

    def check(self, subject: str) -> None:
        window = int(time.time()) // self.window_seconds
        key = f"mcp-rate:{subject}:{window}"
        if cache.add(key, 1, timeout=self.window_seconds + 1):
            return
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=self.window_seconds + 1)
            return
        if count > self.limit:
            raise PermissionError("MCP request rate limit exceeded.")
