from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.index.models import Provider
from apps.sync.providers.anilist import AniListClient
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


def test_vndb_catalog_discovery_is_page_based_and_id_only() -> None:
    http_client = Mock()
    response = http_client.post.return_value
    response.json.return_value = {
        "results": [{"id": "v1"}, {"id": "v2"}],
        "more": True,
        "count": 42,
    }
    with patch("apps.sync.providers.vndb.Provider.objects.filter") as provider_filter:
        provider_filter.return_value.first.return_value = None
        page = VNDBClient(http_client).discover_vn_page(cursor="3", page_size=25)

    assert page.external_ids == ("v1", "v2")
    assert page.next_cursor == "4"
    assert page.total_count == 42
    request = http_client.post.call_args.kwargs["json"]
    assert request["fields"] == "id"
    assert request["page"] == 3
    assert request["results"] == 25


def test_anilist_catalog_discovery_uses_page_info() -> None:
    http_client = Mock()
    response = http_client.post.return_value
    response.json.return_value = {
        "data": {
            "Page": {
                "pageInfo": {"hasNextPage": False, "total": 2},
                "media": [{"id": 10}, {"id": 11}],
            }
        }
    }
    with patch(
        "apps.sync.providers.anilist.Provider.objects.filter"
    ) as provider_filter:
        provider_filter.return_value.first.return_value = None
        page = AniListClient(http_client).discover_anime_page(cursor="2", page_size=25)

    assert page.external_ids == ("10", "11")
    assert page.next_cursor is None
    assert page.total_count == 2
