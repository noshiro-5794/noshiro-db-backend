from datetime import date
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from apps.users.api.serializers.collections import (
    CollectionListRequestSerializer,
)
from apps.users.api.serializers.contracts import (
    LibraryEntryQuerySerializer,
    PublicLibraryQuerySerializer,
)
from apps.users.api.serializers.profile import (
    ProfileStatsRequestSerializer,
    UserSettingsUpdateRequestSerializer,
)
from apps.users.exceptions import InvalidWatchDateRange, UserNotFound
from apps.users.models import User, UserSubject
from apps.users.selectors.public.public_profile_selector import PublicProfileSelector
from apps.users.services.library.subject_service import UserSubjectService


def test_profile_stats_reject_unknown_timezones() -> None:
    serializer = ProfileStatsRequestSerializer(data={"timezone": "Mars/Olympus"})

    assert not serializer.is_valid()
    assert "timezone" in serializer.errors


def test_adult_content_requires_explicit_confirmation() -> None:
    serializer = UserSettingsUpdateRequestSerializer(data={"show_adult_content": True})

    assert not serializer.is_valid()
    assert "confirm_adult_content" in serializer.errors


@pytest.mark.django_db
def test_confirming_adult_content_records_the_confirmation_time() -> None:
    user = User.objects.create_user(email="adult-settings@example.com")
    client = APIClient()
    client.force_authenticate(user)

    before = timezone.now()
    response = client.patch(
        "/api/v1/users/me/settings/",
        {
            "show_adult_content": True,
            "confirm_adult_content": True,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["show_adult_content"] is True
    user.profile.refresh_from_db()
    assert user.profile.adult_content_confirmed_at is not None
    assert user.profile.adult_content_confirmed_at >= before


def test_user_list_queries_reject_unknown_filters() -> None:
    my_library = LibraryEntryQuerySerializer(data={"status": "unknown"})
    public_library = PublicLibraryQuerySerializer(data={"status": "unknown"})
    collections = CollectionListRequestSerializer(data={"ordering": "random"})

    assert not my_library.is_valid()
    assert not public_library.is_valid()
    assert not collections.is_valid()


def test_watch_dates_use_native_date_fields_and_a_range_constraint() -> None:
    assert isinstance(UserSubject._meta.get_field("watch_start_date"), models.DateField)
    assert isinstance(UserSubject._meta.get_field("watch_end_date"), models.DateField)
    assert "ck_watch_date_range" in {
        constraint.name for constraint in UserSubject._meta.constraints
    }


def test_watch_date_normalization_is_strict() -> None:
    assert UserSubjectService._normalize_watch_date("2026-07-27") == date(2026, 7, 27)

    with pytest.raises(InvalidWatchDateRange):
        UserSubjectService._normalize_watch_date("27/07/2026")

    with pytest.raises(InvalidWatchDateRange):
        UserSubjectService._validate_watch_date_range(
            watch_start_date=date(2026, 7, 28),
            watch_end_date=date(2026, 7, 27),
        )


@pytest.mark.django_db
def test_blacklisted_refresh_tokens_return_unauthorized() -> None:
    user = User.objects.create_user(email="blacklisted-refresh@example.com")
    refresh = RefreshToken.for_user(user)
    refresh.blacklist()

    client = APIClient()
    client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
    response = client.post("/api/v1/auth/sessions/refresh/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["type"] == "about:blank"
    assert response.data["title"] == "Unauthorized"
    assert response.data["status"] == 401
    assert response.data["detail"] == "Token is blacklisted"
    assert response.data["instance"] == "/api/v1/auth/sessions/refresh/"
    assert response.data["trace_id"] == response["X-Request-ID"]
    assert response["Content-Type"] == "application/problem+json"


@pytest.mark.django_db
def test_password_change_revokes_existing_access_and_refresh_tokens() -> None:
    user = User.objects.create_user(
        email="password-change@example.com",
        password="old-password",
    )
    refresh = RefreshToken.for_user(user)
    access = str(refresh.access_token)
    refresh_value = str(refresh)

    user.set_password("new-password")
    user.save(update_fields=["password"])

    api_client = APIClient()
    response = api_client.get(
        "/api/v1/users/me/profile/",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    api_client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = refresh_value
    response = api_client.post("/api/v1/auth/sessions/refresh/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_legacy_refresh_token_is_upgraded_once_without_logging_out_the_user() -> None:
    user = User.objects.create_user(
        email="legacy-refresh@example.com",
        password="current-password",
    )
    legacy_refresh = RefreshToken.for_user(user)
    del legacy_refresh[api_settings.REVOKE_TOKEN_CLAIM]
    legacy_value = str(legacy_refresh)

    client = APIClient()
    client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = legacy_value
    response = client.post("/api/v1/auth/sessions/refresh/")

    assert response.status_code == status.HTTP_200_OK
    expected_fingerprint = get_md5_hash_password(user.password)
    assert (
        AccessToken(response.data["access"])[api_settings.REVOKE_TOKEN_CLAIM]
        == expected_fingerprint
    )
    rotated = RefreshToken(response.cookies[settings.JWT_REFRESH_COOKIE_NAME].value)
    assert rotated[api_settings.REVOKE_TOKEN_CLAIM] == expected_fingerprint
    assert BlacklistedToken.objects.filter(token__jti=legacy_refresh["jti"]).exists()


@pytest.mark.django_db
def test_password_reset_blacklists_all_outstanding_refresh_tokens() -> None:
    from apps.users.services.auth.password_service import PasswordService

    user = User.objects.create_user(email="revoke-all@example.com")
    RefreshToken.for_user(user)
    RefreshToken.for_user(user)

    PasswordService._revoke_refresh_tokens(user=user)

    assert BlacklistedToken.objects.filter(token__user=user).count() == 2


def test_blocked_public_profiles_are_masked_as_not_found() -> None:
    user = Mock(pk=2)
    viewer = Mock(pk=1, is_authenticated=True)

    with patch(
        "apps.users.selectors.public.public_profile_selector.UserBlock.objects.filter"
    ) as filter_blocks:
        filter_blocks.return_value.exists.return_value = True

        with pytest.raises(UserNotFound):
            PublicProfileSelector._raise_if_blocked(user=user, viewer=viewer)
