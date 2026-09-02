from unittest.mock import Mock

import pytest

from apps.index.models import Provider, ProviderNamespace, ProviderRecord
from apps.sync.providers.anilist import AniListClient
from apps.sync.providers.bangumi import (
    BANGUMI_SOURCE,
    BANGUMI_SUBJECT_NAMESPACE,
    BangumiClient,
    parse_bangumi_cursor,
)
from apps.sync.providers.exceptions import AniListAPIError, VNDBAPIError
from apps.sync.providers.vndb import VNDB_SOURCE, VNDB_VN_NAMESPACE, VNDBClient
from apps.sync.services.campaign_service import (
    PROVIDERS,
    SyncCampaignService,
)
from apps.sync.services.relation_types import canonical_relation_type


def test_provider_http_errors_expose_retry_policy() -> None:
    rate_limited = VNDBAPIError("busy", status_code=429, retry_after=4)
    permanent = AniListAPIError("invalid", status_code=400)

    assert rate_limited.retryable is True
    assert rate_limited.retry_after == 4
    assert rate_limited.error_code == "http_429"
    assert permanent.retryable is False


def test_relation_vocabularies_share_canonical_slugs() -> None:
    assert canonical_relation_type("vndb", "seq") == "sequel"
    assert canonical_relation_type("anilist", "SEQUEL") == "sequel"
    assert canonical_relation_type("bangumi", "续作") == "sequel"


def test_unknown_relation_keeps_a_stable_slug() -> None:
    assert canonical_relation_type("custom", "Official Remake") == "official-remake"


def test_bangumi_cursor_parsing_is_stable() -> None:
    assert parse_bangumi_cursor("2:100") == (2, 100)
    assert parse_bangumi_cursor("6") == (6, 0)
    assert parse_bangumi_cursor(None) == (1, 0)
    assert parse_bangumi_cursor("5:0") == (1, 0)  # type 5 does not exist
    assert parse_bangumi_cursor("2:-1") == (1, 0)
    assert parse_bangumi_cursor("junk") == (1, 0)


def test_bangumi_catalog_discovery_pages_by_type_and_offset() -> None:
    client = BangumiClient(Mock())
    client._get = Mock(
        side_effect=[
            [{"id": 1}, {"id": 2}],  # type 1, short page -> type 2
            [{"id": 10}, {"id": 11}],  # type 2, short page -> type 3
            [{"id": 30}, {"id": 31}, {"id": 32}],  # type 3, full page -> same type
            [{"id": 33}, {"id": 34}],  # type 3, short page -> type 4
            [{"id": 40}],  # type 4, short page -> type 6
            [{"id": 60}],  # type 6, short page -> done
        ]
    )

    pages: list[tuple[tuple[str, ...], str | None]] = []
    cursor = "1:0"
    while cursor:
        page = client.discover_subject_page(cursor=cursor, page_size=3)
        pages.append((page.external_ids, page.next_cursor))
        cursor = page.next_cursor

    assert pages == [
        (("1", "2"), "2:0"),
        (("10", "11"), "3:0"),
        (("30", "31", "32"), "3:3"),
        (("33", "34"), "4:0"),
        (("40",), "6:0"),
        (("60",), None),
    ]
    first_params = client._get.call_args_list[0].kwargs["params"]
    assert first_params == {"type": 1, "limit": 3, "offset": 0, "sort": "date"}


@pytest.mark.django_db
def test_bangumi_delta_refetches_known_active_records() -> None:
    provider = Provider.objects.create(slug=BANGUMI_SOURCE.slug, name="Bangumi")
    namespace = ProviderNamespace.objects.create(
        provider=provider, slug=BANGUMI_SUBJECT_NAMESPACE.slug, resource_type="subject"
    )
    ProviderRecord.objects.create(
        namespace=namespace, external_id="1", origin="api", status="active"
    )
    ProviderRecord.objects.create(
        namespace=namespace, external_id="2", origin="api", status="active"
    )
    client = BangumiClient(Mock())

    page = client.discover_subject_delta_page(watermark="0", cursor="0", page_size=1)

    assert page.external_ids == ("1",)
    assert page.next_cursor == "1"
    assert page.total_count == 2


@pytest.mark.django_db
def test_vndb_delta_refetches_known_active_records() -> None:
    provider = Provider.objects.create(slug=VNDB_SOURCE.slug, name="VNDB")
    namespace = ProviderNamespace.objects.create(
        provider=provider, slug=VNDB_VN_NAMESPACE.slug, resource_type="subject"
    )
    ProviderRecord.objects.create(
        namespace=namespace, external_id="v1", origin="api", status="active"
    )
    client = VNDBClient(Mock())

    page = client.discover_vn_delta_page(watermark="0", cursor="0", page_size=10)

    assert page.external_ids == ("v1",)
    assert page.next_cursor is None
    assert page.total_count == 1


def test_campaign_provider_registry_wires_delta_and_discovery_contract() -> None:
    assert PROVIDERS["vndb"].discover_delta is not None
    assert PROVIDERS["anilist"].discover_delta is not None
    assert PROVIDERS["bangumi"].discover_delta is not None
    assert PROVIDERS["vndb"].discovery_complete is True
    assert PROVIDERS["anilist"].discovery_complete is True
    assert PROVIDERS["bangumi"].discovery_complete is False


def test_anilist_delta_watermark_advances_to_max_seen() -> None:
    client = AniListClient(Mock())
    client._post = Mock(
        return_value={
            "Page": {
                "pageInfo": {"hasNextPage": True},
                "media": [
                    {"id": 1, "updatedAt": 100},
                    {"id": 2, "updatedAt": 120},
                ],
            }
        }
    )

    page = client.discover_anime_delta_page(watermark="90", cursor="1", page_size=50)

    assert page.external_ids == ("1", "2")
    assert page.next_cursor == "2"
    assert page.watermark == "120"
    assert client._post.call_args.args[1] == {
        "page": 1,
        "perPage": 50,
        "updatedAfter": 90,
    }


def test_accumulate_watermark_merges_numeric_deltas() -> None:
    class FakePage:
        watermark: str

        def __init__(self, watermark):
            self.watermark = watermark

    assert SyncCampaignService._accumulate_watermark(None, FakePage("120")) == "120"
    assert SyncCampaignService._accumulate_watermark("100", FakePage("90")) == "100"
    assert SyncCampaignService._accumulate_watermark("100", FakePage("150")) == "150"
    assert (
        SyncCampaignService._accumulate_watermark(
            "100", FakePage("known-record-reconciliation")
        )
        == "100"
    )


def test_missing_reconciliation_requires_provable_complete_discovery() -> None:
    class FakeCampaign:
        def __init__(self, provider_slug, campaign_type="full", parameters=None):
            self.provider_slug = provider_slug
            self.campaign_type = campaign_type
            self.parameters = parameters or {}

    assert (
        SyncCampaignService._can_mark_missing(
            FakeCampaign("vndb", parameters={"discovery": {"next_cursor": None}})
        )
        is True
    )
    assert (
        SyncCampaignService._can_mark_missing(
            FakeCampaign("anilist", parameters={"discovery": {"truncated": True}})
        )
        is False
    )
    assert (
        SyncCampaignService._can_mark_missing(
            FakeCampaign("bangumi", parameters={"discovery": {"next_cursor": None}})
        )
        is False
    )
    assert (
        SyncCampaignService._can_mark_missing(
            FakeCampaign(
                "bangumi",
                parameters={
                    "discovery": {"next_cursor": None},
                    "reconcile_missing": True,
                },
            )
        )
        is True
    )
    assert (
        SyncCampaignService._can_mark_missing(FakeCampaign("anilist", "incremental"))
        is False
    )


def test_incremental_watermark_promoted_only_at_review() -> None:
    class FakeCampaign:
        campaign_type = "incremental"
        parameters = {"pending_watermark": "1700000000"}
        save_calls: list[tuple] = []

        def save(self, **kwargs) -> None:
            self.save_calls.append(kwargs)

    campaign = FakeCampaign()

    SyncCampaignService._promote_watermark(campaign)

    assert campaign.parameters == {"watermark": "1700000000"}
    assert campaign.save_calls == [{"update_fields": ["parameters", "updated_at"]}]


def test_full_campaign_never_promotes_watermark() -> None:
    class FakeCampaign:
        campaign_type = "full"
        parameters = {"pending_watermark": "1700000000"}
        save_calls: list[tuple] = []

        def save(self, **kwargs) -> None:
            self.save_calls.append(kwargs)

    campaign = FakeCampaign()

    SyncCampaignService._promote_watermark(campaign)

    assert campaign.parameters == {"pending_watermark": "1700000000"}
    assert campaign.save_calls == []


def test_truncated_incremental_never_promotes_watermark() -> None:
    class FakeCampaign:
        campaign_type = "incremental"
        parameters = {
            "discovery": {"truncated": True},
            "pending_watermark": "1700000000",
        }
        save_calls: list[tuple] = []

        def save(self, **kwargs) -> None:
            self.save_calls.append(kwargs)

    campaign = FakeCampaign()

    SyncCampaignService._promote_watermark(campaign)

    assert campaign.parameters == {
        "discovery": {"truncated": True},
        "pending_watermark": "1700000000",
    }
    assert campaign.save_calls == []
