from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.index.models import Provider
from apps.sync.providers.bangumi import (
    BANGUMI_SOURCE,
    BangumiAPIError,
    BangumiClient,
)
from apps.sync.providers.vndb import VNDB_SOURCE, VNDBAPIError, VNDBClient


@override_settings(
    BANGUMI_API_BASE_URL="https://api.bgm.tv",
    BANGUMI_API_KEY=None,
    BANGUMI_TIMEOUT=30,
    BANGUMI_USER_AGENT=("Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"),
)
def test_bangumi_http_client_is_created_lazily() -> None:
    with patch("apps.sync.providers.bangumi.httpx.Client") as client_factory:
        client = BangumiClient()

        client_factory.assert_not_called()

        assert client.client is client_factory.return_value
        assert client.client is client_factory.return_value
        client_factory.assert_called_once_with(
            base_url="https://api.bgm.tv",
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"
                ),
            },
            timeout=30,
            follow_redirects=True,
        )


@override_settings(
    BANGUMI_API_BASE_URL="https://api.bgm.tv",
    BANGUMI_API_KEY=None,
    BANGUMI_TIMEOUT=30,
    BANGUMI_USER_AGENT=("Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"),
)
def test_http_client_can_be_recreated_after_close() -> None:
    initial_client = Mock()
    client = BangumiClient(initial_client)

    client.close()
    initial_client.close.assert_called_once_with()

    with patch("apps.sync.providers.bangumi.httpx.Client") as client_factory:
        assert client.client is client_factory.return_value
        client_factory.assert_called_once_with(
            base_url="https://api.bgm.tv",
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Noshiro_5794/noshiro_db (https://github.com/noshiro-5794)"
                ),
            },
            timeout=30,
            follow_redirects=True,
        )


@pytest.mark.django_db
def test_disabled_bangumi_provider_is_not_requested() -> None:
    Provider.objects.create(
        slug=BANGUMI_SOURCE.slug,
        name=BANGUMI_SOURCE.name,
        is_enabled=False,
    )
    http_client = Mock()
    client = BangumiClient(http_client)

    with pytest.raises(BangumiAPIError, match="provider is disabled"):
        client.fetch_subject(1)

    http_client.get.assert_not_called()


@pytest.mark.django_db
def test_disabled_vndb_provider_is_not_requested() -> None:
    Provider.objects.create(
        slug=VNDB_SOURCE.slug,
        name=VNDB_SOURCE.name,
        is_enabled=False,
    )
    http_client = Mock()
    client = VNDBClient(http_client)

    with pytest.raises(VNDBAPIError, match="provider is disabled"):
        client.fetch_vn("v1")

    http_client.post.assert_not_called()


@pytest.mark.parametrize(
    ("source", "client_factory", "fetch", "request_method", "error"),
    [
        (
            BANGUMI_SOURCE,
            BangumiClient,
            lambda client: client.fetch_subject(1),
            "get",
            BangumiAPIError,
        ),
        (
            VNDB_SOURCE,
            VNDBClient,
            lambda client: client.fetch_vn("v1"),
            "post",
            VNDBAPIError,
        ),
    ],
)
@pytest.mark.django_db
def test_forbidden_storage_provider_is_not_requested(
    source, client_factory, fetch, request_method, error
) -> None:
    Provider.objects.create(
        slug=source.slug,
        name=source.name,
        storage_policy=Provider.UsagePolicy.FORBIDDEN,
    )
    http_client = Mock()

    with pytest.raises(error, match="forbids source payload storage"):
        fetch(client_factory(http_client))

    getattr(http_client, request_method).assert_not_called()
