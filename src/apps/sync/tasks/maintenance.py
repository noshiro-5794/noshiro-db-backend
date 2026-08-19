import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from apps.sync.services.sync_job_service import sync_job_service

logger = logging.getLogger(__name__)


@shared_task(queue="realtime")
def worker_heartbeat() -> dict:
    now = timezone.now()
    cache.set("noshiro:beat:heartbeat", now.isoformat(), timeout=180)
    return {"heartbeat_at": now.isoformat()}


@shared_task(queue="realtime")
def scan_stale_sync_jobs() -> dict:
    now = timezone.now()
    stale_jobs = list(
        sync_job_service.stale_running_jobs(before=now).values_list(
            "id", "lease_owner", "attempt", "celery_task_id"
        )
    )
    for job_id, lease_owner, attempt, celery_task_id in stale_jobs:
        sync_job_service.mark_failed(
            job_id=job_id,
            error=(
                f"Lease expired while running (attempt={attempt}, "
                f"lease_owner={lease_owner or ''}, celery_task_id={celery_task_id})."
            ),
            current_label="Lease expired",
        )
        logger.warning(
            "Stale sync job marked failed",
            extra={"job_id": str(job_id), "lease_owner": lease_owner},
        )
    return {"stale_jobs": len(stale_jobs)}
