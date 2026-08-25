from celery import shared_task

from apps.sync.models import SyncCampaign
from apps.sync.services.campaign_service import sync_campaign_service


@shared_task(soft_time_limit=3600, time_limit=3660)
def run_sync_campaign_task(
    campaign_id: str,
    *,
    max_items: int | None = None,
) -> dict:
    """Execute one durable campaign and return its persisted status."""
    campaign = SyncCampaign.objects.get(pk=campaign_id)
    result = sync_campaign_service.run(campaign, max_items=max_items)
    return {
        "campaign_id": str(result.pk),
        "provider": result.provider_slug,
        "status": result.status,
        "processed_items": result.processed_items,
        "failed_items": result.failed_items,
    }
