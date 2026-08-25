import pytest

from apps.sync.services.campaign_service import (
    CampaignProviderNotFound,
    SyncCampaignService,
    campaign_idempotency_key,
)


def test_campaign_idempotency_key_is_stable_for_mapping_equivalent_parameters() -> None:
    first = campaign_idempotency_key(
        provider_slug="vndb",
        campaign_type="full",
        parameters={"page_size": 100, "ai_sample_size": 16},
    )
    second = campaign_idempotency_key(
        provider_slug="vndb",
        campaign_type="full",
        parameters={"ai_sample_size": 16, "page_size": 100},
    )

    assert first == second
    assert first.startswith("vndb:full:")


def test_campaign_service_rejects_unregistered_provider() -> None:
    with pytest.raises(CampaignProviderNotFound, match="Unsupported campaign provider"):
        SyncCampaignService().provider_for("unknown")


def test_campaign_service_taxonomy_values_are_unique_and_bounded() -> None:
    values = SyncCampaignService._taxonomy_values(
        {
            "genres": ["Action", "Action", ""],
            "tags": [{"name": "Drama"}, "Drama", {"name": None}],
        }
    )

    assert values == ("Action", "Drama")
