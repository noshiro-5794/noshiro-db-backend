import uuid
from unittest.mock import patch

import pytest

from apps.sync.models import SyncCampaign, SyncWorkItem
from apps.sync.services.campaign_service import sync_campaign_service

pytestmark = pytest.mark.django_db(transaction=True)


def _work_item(campaign: SyncCampaign, *, shard: int) -> SyncWorkItem:
    return SyncWorkItem.objects.create(
        campaign=campaign,
        shard=shard,
        cursor=str(shard),
        status=SyncWorkItem.Status.SUCCEEDED,
        result={"entity_id": str(uuid.uuid4())},
    )


def test_enrich_phase_is_bounded_and_tracks_stats() -> None:
    campaign = SyncCampaign.objects.create(
        provider_slug="bangumi",
        campaign_type="full",
        ai_mode=SyncCampaign.AIMode.SHADOW,
        parameters={"enrich_sample_size": 3, "ai_batch_size": 2},
    )
    for shard in range(4):
        _work_item(campaign, shard=shard)

    with patch.object(
        sync_campaign_service,
        "_enrich_item",
        return_value={"claims": 2, "applied": 1, "abstained": 0, "skipped": 0},
    ) as mock:
        done = sync_campaign_service._enrich(campaign)

    assert done is False  # sample of 3 consumed; one item remains
    assert mock.call_count == 3
    assert (
        SyncWorkItem.objects.filter(
            campaign=campaign, ai_enriched_at__isnull=False
        ).count()
        == 3
    )
    campaign.refresh_from_db()
    assert campaign.parameters["enrichment"] == {
        "claims": 6,
        "applied": 3,
        "abstained": 0,
        "skipped": 0,
    }

    with patch.object(
        sync_campaign_service,
        "_enrich_item",
        return_value={"claims": 2, "applied": 1, "abstained": 0, "skipped": 0},
    ) as mock:
        done = sync_campaign_service._enrich(campaign)

    assert done is True
    assert mock.call_count == 1
    assert (
        SyncWorkItem.objects.filter(
            campaign=campaign, ai_enriched_at__isnull=False
        ).count()
        == 4
    )


def test_enrich_phase_is_skipped_when_ai_is_off() -> None:
    campaign = SyncCampaign.objects.create(
        provider_slug="bangumi",
        campaign_type="full",
        ai_mode=SyncCampaign.AIMode.OFF,
        parameters={},
    )
    _work_item(campaign, shard=1)

    with patch.object(
        sync_campaign_service,
        "_enrich_item",
        return_value={"claims": 2, "applied": 1, "abstained": 0, "skipped": 0},
    ) as mock:
        done = sync_campaign_service._enrich(campaign)

    assert done is True
    mock.assert_not_called()
    assert (
        SyncWorkItem.objects.filter(
            campaign=campaign, ai_enriched_at__isnull=True
        ).count()
        == 1
    )


def test_enrich_item_skips_when_entity_is_missing() -> None:
    campaign = SyncCampaign.objects.create(
        provider_slug="bangumi",
        campaign_type="full",
        ai_mode=SyncCampaign.AIMode.SHADOW,
        parameters={},
    )
    item = _work_item(campaign, shard=1)

    with patch(
        "apps.sync.services.campaign_service.sync_ai_service.enrich_entity"
    ) as mock:
        result = sync_campaign_service._enrich_item(
            campaign,
            item,
            apply=False,
            min_confidence=0.85,
            languages=("zh", "ja", "en"),
        )

    assert result == {"claims": 0, "applied": 0, "abstained": 0, "skipped": 1}
    mock.assert_not_called()
