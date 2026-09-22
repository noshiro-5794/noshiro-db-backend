from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.index.models import Provider
from apps.sync.providers.exceptions import MALAPIError
from apps.sync.providers.mal import (
    MAL_ANIME_NAMESPACE,
    MAL_SCHEDULE_ITEM_NAMESPACE,
    MAL_SEASON_NAMESPACE,
    MAL_SOURCE,
    MALAPIClient,
    season_name_for_quarter,
)


def test_mal_namespace_specs_reference_mal_provider() -> None:
    assert MAL_SOURCE.slug == "mal"
    assert MAL_ANIME_NAMESPACE.slug == "anime"
    assert MAL_SCHEDULE_ITEM_NAMESPACE.slug == "schedule-item"
    assert MAL_SEASON_NAMESPACE.slug == "season"
    assert all(
        spec.source.slug == "mal"
        for spec in (
            MAL_ANIME_NAMESPACE,
            MAL_SCHEDULE_ITEM_NAMESPACE,
            MAL_SEASON_NAMESPACE,
        )
    )


def test_quarter_maps_to_mal_season_name() -> None:
    assert season_name_for_quarter(1) == "winter"
    assert season_name_for_quarter(3) == "summer"
    with pytest.raises(ValueError, match="between 1 and 4"):
        season_name_for_quarter(5)


@override_settings(
    MAL_API_BASE_URL="https://api.myanimelist.net/v2",
    MAL_API_CLIENT_ID="test-client-id",
    MAL_USER_AGENT="noshiro-db-test (+https://example.test/contact)",
    MAL_TIMEOUT=30,
    MAL_RATE_LIMIT_INTERVAL=0.1,
)
def test_mal_http_client_is_created_lazily_with_client_id_header() -> None:
    with patch("apps.sync.providers.mal.httpx.Client") as client_factory:
        client = MALAPIClient()

        client_factory.assert_not_called()

        assert client.client is client_factory.return_value
        client_factory.assert_called_once_with(
            base_url="https://api.myanimelist.net/v2",
            headers={
                "Accept": "application/json",
                "X-MAL-CLIENT-ID": "test-client-id",
                "User-Agent": ("noshiro-db-test (+https://example.test/contact)"),
            },
            timeout=30,
            follow_redirects=True,
        )


@override_settings(
    MAL_API_BASE_URL="https://api.myanimelist.net/v2",
    MAL_API_CLIENT_ID=None,
    MAL_USER_AGENT="agent",
    MAL_TIMEOUT=30,
    MAL_RATE_LIMIT_INTERVAL=0.1,
)
def test_mal_client_requires_configured_client_id() -> None:
    with pytest.raises(MALAPIError, match="MAL_API_CLIENT_ID is not configured"):
        assert MALAPIClient().client


def test_mal_anime_detail_is_returned_unwrapped() -> None:
    http_client = Mock()
    response = http_client.get.return_value
    response.json.return_value = {
        "id": 60636,
        "title": "Bleach: Sennen Kessen-hen - Kashin-tan",
    }
    with patch("apps.sync.providers.mal.Provider.objects.filter") as provider_filter:
        provider_filter.return_value.first.return_value = None
        anime = MALAPIClient(http_client).fetch_anime(60636)

    assert anime["title"] == "Bleach: Sennen Kessen-hen - Kashin-tan"
    request = http_client.get.call_args
    assert request.args == ("/anime/60636",)
    assert "id,title,main_picture" in request.kwargs["params"]["fields"]
    assert request.kwargs["params"]["fields"].endswith("studios")


def test_mal_season_request_uses_offset_pagination_and_nsfw() -> None:
    http_client = Mock()
    response = http_client.get.return_value
    response.json.return_value = {
        "data": [
            {"node": {"id": 60636, "title": "Bleach"}},
            {"node": {"id": 21, "title": "One Piece"}},
        ],
        "paging": {"next": "https://api.myanimelist.net/v2/anime/season/2026/summer"},
        "season": {"year": 2026, "season": "summer"},
    }
    with patch("apps.sync.providers.mal.Provider.objects.filter") as provider_filter:
        provider_filter.return_value.first.return_value = None
        payload = MALAPIClient(http_client).fetch_season(
            year=2026,
            season="summer",
            offset=500,
            limit=999,
        )

    assert payload["season"]["season"] == "summer"
    request = http_client.get.call_args
    assert request.args == ("/anime/season/2026/summer",)
    assert request.kwargs["params"] == {
        "limit": 500,
        "offset": 500,
        "fields": request.kwargs["params"]["fields"],
        "nsfw": "true",
    }


def test_mal_search_requests_official_endpoint() -> None:
    http_client = Mock()
    response = http_client.get.return_value
    response.json.return_value = {"data": [{"node": {"id": 21, "title": "One Piece"}}]}
    with patch("apps.sync.providers.mal.Provider.objects.filter") as provider_filter:
        provider_filter.return_value.first.return_value = None
        payload = MALAPIClient(http_client).search_anime(query="one piece", limit=3)

    assert payload["data"][0]["node"]["id"] == 21
    request = http_client.get.call_args
    assert request.args == ("/anime",)
    assert request.kwargs["params"] == {
        "q": "one piece",
        "limit": 3,
        "offset": 0,
        "fields": request.kwargs["params"]["fields"],
        "nsfw": "true",
    }


def test_http_client_can_be_recreated_after_close() -> None:
    initial_client = Mock()
    client = MALAPIClient(initial_client)

    client.close()
    initial_client.close.assert_called_once_with()

    with (
        override_settings(
            MAL_API_BASE_URL="https://api.myanimelist.net/v2",
            MAL_API_CLIENT_ID="test-client-id",
            MAL_USER_AGENT="agent",
            MAL_TIMEOUT=30,
            MAL_RATE_LIMIT_INTERVAL=0.1,
        ),
        patch("apps.sync.providers.mal.httpx.Client") as client_factory,
    ):
        assert client.client is client_factory.return_value
    client_factory.assert_called_once()


@pytest.mark.django_db
def test_disabled_mal_provider_is_not_requested() -> None:
    Provider.objects.create(
        slug=MAL_SOURCE.slug,
        name=MAL_SOURCE.name,
        is_enabled=False,
    )
    http_client = Mock()

    with pytest.raises(MALAPIError, match="provider is disabled"):
        MALAPIClient(http_client).fetch_anime(60636)

    http_client.get.assert_not_called()


@pytest.mark.django_db
def test_forbidden_mal_storage_is_not_requested() -> None:
    Provider.objects.create(
        slug=MAL_SOURCE.slug,
        name=MAL_SOURCE.name,
        storage_policy=Provider.UsagePolicy.FORBIDDEN,
    )
    http_client = Mock()

    with pytest.raises(MALAPIError, match="forbids source payload storage"):
        MALAPIClient(http_client).fetch_anime(60636)

    http_client.get.assert_not_called()
