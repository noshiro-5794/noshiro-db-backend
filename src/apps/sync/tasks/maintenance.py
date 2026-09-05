import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.sync.models import SyncState
from apps.sync.services.incremental_sync_service import IncrementalSyncService
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


@shared_task(queue="realtime")
def scan_stale_sync_states() -> dict:
    """Unlock legacy incremental windows whose worker died mid-window.

    Legacy ``sync_state`` rows are the only frontier lock for the incremental
    tasks. A worker that dies while running leaves the row RUNNING forever,
    which aborts every later ``sync_all`` (SyncTaskAlreadyRunning). Progress is
    timestamped by ``_record_progress``, so a RUNNING row older than the
    threshold is stale and safe to unlock.
    """
    cutoff = timezone.now() - timedelta(
        seconds=max(60, settings.SYNC_STALE_STATE_SECONDS)
    )
    stale_names = list(
        SyncState.objects.filter(
            shard=IncrementalSyncService.SHARD,
            task_name__in=list(IncrementalSyncService.TASKS),
            status=SyncState.Status.RUNNING,
            updated_at__lt=cutoff,
        ).values_list("task_name", flat=True)
    )
    for task_name in stale_names:
        IncrementalSyncService.unlock_running(task_name=task_name)
        logger.warning(
            "Stale incremental sync state unlocked",
            extra={"task_name": task_name},
        )
    return {"stale_states": len(stale_names)}
