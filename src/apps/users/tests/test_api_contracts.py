from datetime import date
from unittest.mock import Mock, patch

import pytest
from django.conf import settings
from django.db import models
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError

from apps.users.api.serializers.library.collection_serializer import (
    CollectionListRequestSerializer,
)
from apps.users.api.serializers.library.subject_serializer import (
    UserSubjectListRequestSerializer,
)
from apps.users.api.serializers.profile.profile_serializer import (
    ProfileStatsRequestSerializer,
)
from apps.users.api.serializers.public.public_profile_serializer import (
    PublicUserSubjectListRequestSerializer,
)
from apps.users.exceptions import InvalidWatchDateRange, UserNotFound
from apps.users.models import UserSubject
from apps.users.selectors.public.public_profile_selector import PublicProfileSelector
from apps.users.services.library.subject_service import UserSubjectService


def test_profile_stats_reject_unknown_timezones() -> None:
    serializer = ProfileStatsRequestSerializer(data={"timezone": "Mars/Olympus"})

    assert not serializer.is_valid()
    assert "timezone" in serializer.errors


def test_user_list_queries_reject_unknown_filters() -> None:
    my_subjects = UserSubjectListRequestSerializer(
        data={"status": "unknown", "tag_id": "not-an-integer"}
    )
    public_subjects = PublicUserSubjectListRequestSerializer(
        data={"subject_type": "unknown", "ordering": "email"}
    )
    collections = CollectionListRequestSerializer(data={"ordering": "random"})

    assert not my_subjects.is_valid()
    assert not public_subjects.is_valid()
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


def test_blacklisted_refresh_tokens_return_unauthorized() -> None:
    client = APIClient()
    client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = "blacklisted-refresh-token"

    with patch(
        "apps.users.services.auth.token_service.TokenRefreshSerializer"
    ) as serializer_class:
        serializer_class.return_value.is_valid.side_effect = TokenError(
            "Token is blacklisted"
        )
        response = client.post("/api/users/token/refresh/")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == 40100
    assert response.data["message"] == "Token is blacklisted"
    assert str(response.data["data"]["detail"]) == "Token is blacklisted"


def test_blocked_public_profiles_are_masked_as_not_found() -> None:
    user = Mock(pk=2)
    viewer = Mock(pk=1, is_authenticated=True)

    with patch(
        "apps.users.selectors.public.public_profile_selector.UserBlock.objects.filter"
    ) as filter_blocks:
        filter_blocks.return_value.exists.return_value = True

        with pytest.raises(UserNotFound):
            PublicProfileSelector._raise_if_blocked(user=user, viewer=viewer)
