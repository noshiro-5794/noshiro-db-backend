from unittest.mock import Mock, patch

import httpx
import pytest
from django.test import override_settings

from apps.index.models import Provider
from apps.sync.providers.anilist import AniListClient
from apps.sync.providers.bangumi import (
    BANGUMI_SOURCE,
    BangumiAPIError,
    BangumiClient,
)
from apps.sync.providers.exceptions import AniListAPIError
from apps.sync.providers.vndb import VNDB_SOURCE, VNDBAPIError, VNDBClient


@override_settings(
    BANGUMI_API_BASE_URL="https://api.bgm.tv",
    BANGUMI_API_KEY=None,
    BANGUMI_TIMEOUT=30,
    BANGUMI_USER_AGENT=("noshiro-db-test (+https://example.test/contact)"),
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
                "User-Agent": ("noshiro-db-test (+https://example.test/contact)"),
            },
            timeout=30,
            follow_redirects=True,
        )


@override_settings(
    BANGUMI_API_BASE_URL="https://api.bgm.tv",
    BANGUMI_API_KEY=None,
    BANGUMI_TIMEOUT=30,
    BANGUMI_USER_AGENT=("noshiro-db-test (+https://example.test/contact)"),
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
                "User-Agent": ("noshiro-db-test (+https://example.test/contact)"),
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


def test_vndb_catalog_discovery_is_page_based_and_counts_on_first_page() -> None:
    http_client = Mock()
    response = http_client.post.return_value
    response.json.return_value = {
        "results": [{"id": "v1"}, {"id": "v2"}],
        "more": True,
        "count": 42,
    }
    with patch("apps.sync.providers.vndb.Provider.objects.filter") as provider_filter:
        provider_filter.return_value.first.return_value = None
        page = VNDBClient(http_client).discover_vn_page(cursor="1", page_size=25)

    assert page.external_ids == ("v1", "v2")
    assert page.next_cursor == "2"
    assert page.total_count == 42
    request = http_client.post.call_args.kwargs["json"]
    assert request["fields"] == "id"
    assert request["page"] == 1
    assert request["results"] == 25
    assert request["count"] is True


def test_bangumi_subject_search_posts_v0_search_contract() -> None:
    http_client = Mock()
    response = http_client.post.return_value
    response.json.return_value = {
        "data": [
            {
                "id": 23456,
                "name": "Test Anime",
                "name_cn": "测试动画",
                "date": "2026-04-01",
                "summary": "…",
            }
        ],
        "total": 1,
        "limit": 5,
        "offset": 0,
    }
    with patch(
        "apps.sync.providers.bangumi.Provider.objects.filter"
    ) as provider_filter:
        provider_filter.return_value.first.return_value = None
        payload = BangumiClient(http_client).search_subjects(
            keyword="Test Anime",
            subject_types=(2,),
            limit=5,
            offset=0,
        )

    assert payload["data"][0]["id"] == 23456
    request = http_client.post.call_args
    assert request.kwargs["params"] == {"limit": 5, "offset": 0}
    assert request.kwargs["json"] == {
        "keyword": "Test Anime",
        "sort": "match",
        "filter": {"type": [2]},
    }


def test_vndb_catalog_discovery_skips_expensive_count_after_first_page() -> None:
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
    assert page.total_count is None
    request = http_client.post.call_args.kwargs["json"]
    assert request["page"] == 3
    assert request["count"] is False


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


@pytest.mark.django_db
def test_anilist_maintenance_403_is_unavailable_not_permanent() -> None:
    http_client = Mock()
    request = httpx.Request("POST", "https://graphql.anilist.co")
    response = httpx.Response(
        403,
        request=request,
        text=(
            '{"errors":[{"message":"The AniList API has been temporarily '
            'disabled due to severe stability issues.","status":403,'
            '"locations":[]}],"data":null}'
        ),
    )
    http_client.post.side_effect = httpx.HTTPStatusError(
        "403 Forbidden",
        request=request,
        response=response,
    )

    with (
        patch("apps.sync.providers.anilist.Provider.objects.filter") as provider_filter,
        patch("apps.sync.providers.anilist.time.sleep") as sleep,
        pytest.raises(AniListAPIError) as exc_info,
    ):
        provider_filter.return_value.first.return_value = None
        AniListClient(http_client).discover_anime_page(cursor="1", page_size=25)

    error = exc_info.value
    assert isinstance(error, AniListAPIError)
    assert error.status_code == 403
    assert error.retryable is True
    assert error.unavailable_reason == "provider_maintenance"
    http_client.post.assert_called_once()
    sleep.assert_not_called()


def test_anilist_delta_discovery_uses_updated_watermark() -> None:
    http_client = Mock()
    response = http_client.post.return_value
    response.json.return_value = {
        "data": {
            "Page": {
                "pageInfo": {"hasNextPage": True},
                "media": [{"id": 10, "updatedAt": 1700000000}],
            }
        }
    }
    with patch(
        "apps.sync.providers.anilist.Provider.objects.filter"
    ) as provider_filter:
        provider_filter.return_value.first.return_value = None
        page = AniListClient(http_client).discover_anime_delta_page(
            watermark="1690000000", cursor="2", page_size=25
        )

    assert page.external_ids == ("10",)
    assert page.next_cursor == "3"
    assert page.watermark == "1700000000"
    variables = http_client.post.call_args.kwargs["json"]["variables"]
    assert variables == {"page": 2, "perPage": 25, "updatedAfter": 1690000000}


def test_vndb_embedded_staff_ids_are_unique() -> None:
    from apps.sync.providers.vndb import VNDBClient

    work = {
        "staff": [{"id": 1}, {"id": 2}, {"x": 1}],
        "va": [{"staff": {"id": 2}}, {"staff": {"id": 3}}, {"nope": 1}],
    }
    assert VNDBClient._embedded_staff_ids(work) == (1, 2, 3)


def test_vndb_staff_details_fetch_by_scalar_id() -> None:
    from apps.sync.providers.vndb import VNDBClient

    client = VNDBClient(Mock())
    work = {
        "staff": [{"id": 7}],
        "va": [{"staff": {"id": 8}}],
    }
    with patch.object(
        client,
        "query",
        side_effect=[
            {"results": [{"id": 7, "name": "A"}], "more": False},
            {"results": [{"id": 8, "name": "B"}], "more": False},
        ],
    ) as query:
        details = client._fetch_staff_details(work)

    assert [item["id"] for item in details] == [7, 8]
    calls = [call.kwargs["filters"] for call in query.call_args_list]
    assert calls == [["id", "=", 7], ["id", "=", 8]]


def test_vndb_release_resolution_is_always_json() -> None:
    from unittest.mock import patch

    from apps.index.models import Predicate
    from apps.sync.services.vndb_service import VNDBImportService

    captured = []

    def fake_record_fact(
        *, entity, observation, slug, name, value, value_type, **kwargs
    ):
        captured.append((slug, value_type, value))
        return None

    with patch(
        "apps.sync.services.vndb_service.knowledge_ingestion_service.record_fact",
        side_effect=fake_record_fact,
    ):
        VNDBImportService()._upsert_release_resolution(
            entity=None,
            observation=None,
            data={"resolution": "1920x1080"},
        )
        VNDBImportService()._upsert_release_resolution(
            entity=None,
            observation=None,
            data={"resolution": ["640x480", "1920x1080"]},
        )

    assert [(slug, value_type) for slug, value_type, _ in captured] == [
        ("release-resolution", Predicate.ValueType.JSON),
        ("release-resolution", Predicate.ValueType.JSON),
    ]
    assert captured[0][2] == {"value": "1920x1080"}
