from contextlib import suppress

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User


class TokenService:
    @staticmethod
    def create_tokens(user: User) -> dict:
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

    @staticmethod
    def set_refresh_cookie(response: Response, refresh_token: str) -> None:
        response.set_cookie(
            key=settings.JWT_REFRESH_COOKIE_NAME,
            value=refresh_token,
            max_age=settings.JWT_REFRESH_COOKIE_MAX_AGE,
            path=settings.JWT_REFRESH_COOKIE_PATH,
            domain=settings.JWT_REFRESH_COOKIE_DOMAIN,
            secure=settings.JWT_REFRESH_COOKIE_SECURE,
            httponly=settings.JWT_REFRESH_COOKIE_HTTP_ONLY,
            samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        )

    @staticmethod
    def clear_refresh_cookie(response: Response) -> None:
        response.delete_cookie(
            key=settings.JWT_REFRESH_COOKIE_NAME,
            path=settings.JWT_REFRESH_COOKIE_PATH,
            domain=settings.JWT_REFRESH_COOKIE_DOMAIN,
            samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        )

    @staticmethod
    def get_refresh_token_from_cookie(request) -> str:
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not refresh:
            raise AuthenticationFailed("refresh token cookie is missing")
        return refresh

    @staticmethod
    def get_optional_refresh_token_from_cookie(request) -> str | None:
        return request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)

    @classmethod
    def rotate_refresh_token(cls, refresh_token: str) -> dict:
        serializer = TokenRefreshSerializer(data={"refresh": refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc
        return serializer.validated_data

    @staticmethod
    def blacklist_refresh_token(refresh_token: str) -> None:
        with suppress(TokenError):
            RefreshToken(refresh_token).blacklist()
