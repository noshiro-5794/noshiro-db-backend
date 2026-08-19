from unittest.mock import Mock

import pytest
from django.urls import Resolver404, resolve
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate


@pytest.mark.parametrize(
    "path",
    (
        "/api/index/",
        "/api/users/",
        "/api/community/",
        "/api/sync/",
        "/api/v2/",
    ),
)
def test_removed_api_roots_do_not_resolve(path: str) -> None:
    with pytest.raises(Resolver404):
        resolve(path)


def test_supported_api_resources_use_the_only_versioned_root() -> None:
    supported_paths = (
        "/health/live/",
        "/health/ready/",
        "/api/v1/index/entities/",
        "/api/v1/auth/sessions/refresh/",
        "/api/v1/users/me/library/entries/",
        "/api/v1/community/posts/",
        "/api/v1/operations/import-jobs/",
        "/api/v1/openapi/",
    )

    for path in supported_paths:
        assert resolve(path).func is not None


@pytest.mark.parametrize("method", ("patch", "post"))
def test_notification_read_state_rejects_removed_compatibility_methods(
    method: str,
) -> None:
    path = "/api/v1/community/me/notifications/1/read-state/"
    match = resolve(path)
    request = getattr(APIRequestFactory(), method)(path)
    force_authenticate(request, user=Mock(is_authenticated=True))

    response = match.func(request, **match.kwargs)

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
