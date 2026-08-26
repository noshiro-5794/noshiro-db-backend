from celery import shared_task
from django.utils import timezone

from apps.sync.models import SyncCampaign
from apps.sync.services.campaign_service import sync_campaign_service


@shared_task(soft_time_limit=300, time_limit=360)
def run_sync_campaign_task(
    campaign_id: str,
    *,
    max_items: int | None = None,
) -> dict:
    """Execute one durable campaign and return its persisted status."""
    campaign = SyncCampaign.objects.get(pk=campaign_id)
    result = sync_campaign_service.run(campaign, max_items=max_items)
    if result.status not in {
        SyncCampaign.Status.COMPLETED,
        SyncCampaign.Status.FAILED,
        SyncCampaign.Status.CANCELLED,
        SyncCampaign.Status.PAUSED,
    }:
        delay = max(1, int((result.parameters or {}).get("step_delay_seconds", 1)))
        retry_at = (
            result.work_items.filter(status="queued", next_retry_at__gt=timezone.now())
            .order_by("next_retry_at")
            .values_list("next_retry_at", flat=True)
            .first()
        )
        if retry_at is not None:
            delay = max(delay, int((retry_at - timezone.now()).total_seconds()))
        result.next_run_at = timezone.now()
        result.save(update_fields=["next_run_at", "updated_at"])
        run_sync_campaign_task.apply_async(
            args=[str(result.pk)],
            kwargs={"max_items": max_items},
            countdown=delay,
        )
    return {
        "campaign_id": str(result.pk),
        "provider": result.provider_slug,
        "status": result.status,
        "processed_items": result.processed_items,
        "failed_items": result.failed_items,
    }
