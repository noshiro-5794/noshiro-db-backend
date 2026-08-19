from contextlib import suppress
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

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
        cookie_options = {
            "key": settings.JWT_REFRESH_COOKIE_NAME,
            "value": refresh_token,
            "max_age": settings.JWT_REFRESH_COOKIE_MAX_AGE,
            "domain": settings.JWT_REFRESH_COOKIE_DOMAIN,
            "secure": settings.JWT_REFRESH_COOKIE_SECURE,
            "httponly": settings.JWT_REFRESH_COOKIE_HTTP_ONLY,
            "samesite": settings.JWT_REFRESH_COOKIE_SAMESITE,
        }
        response.set_cookie(
            path=settings.JWT_REFRESH_COOKIE_PATH,
            **cookie_options,
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
        try:
            token = RefreshToken(refresh_token)
            user = cls._get_token_user(token)
            cls._validate_password_unchanged(token, user)
            cls._add_password_fingerprint(token, user)
            data: dict[str, Any] = {"access": str(token.access_token)}

            if api_settings.ROTATE_REFRESH_TOKENS:
                if api_settings.BLACKLIST_AFTER_ROTATION:
                    with suppress(AttributeError):
                        token.blacklist()
                token.set_jti()
                token.set_exp()
                token.set_iat()
                token.outstand()
                data["refresh"] = str(token)
        except TokenError as exc:
            raise InvalidToken(str(exc)) from exc
        return data

    @staticmethod
    def _get_token_user(token: RefreshToken):
        user_model = get_user_model()
        try:
            user_id = token[api_settings.USER_ID_CLAIM]
            return user_model.objects.only("password", "is_active").get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
        except (KeyError, TokenError, user_model.DoesNotExist) as exc:
            raise InvalidToken("Refresh token is invalid.") from exc

    @staticmethod
    def _validate_password_unchanged(token: RefreshToken, user) -> None:
        if not user.is_active:
            raise AuthenticationFailed(
                "No active account found for the given token.",
                code="no_active_account",
            )
        fingerprint = token.get(api_settings.REVOKE_TOKEN_CLAIM)
        if fingerprint is not None and fingerprint != get_md5_hash_password(
            user.password
        ):
            raise AuthenticationFailed(
                "The user's password has been changed.",
                code="password_changed",
            )

    @staticmethod
    def _add_password_fingerprint(token: RefreshToken, user) -> None:
        if api_settings.CHECK_REVOKE_TOKEN:
            token[api_settings.REVOKE_TOKEN_CLAIM] = get_md5_hash_password(
                user.password
            )

    @staticmethod
    def blacklist_refresh_token(refresh_token: str) -> None:
        with suppress(TokenError):
            RefreshToken(refresh_token).blacklist()
