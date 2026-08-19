from celery import current_task, shared_task

from apps.sync.services.calendar_service import calendar_sync_service
from apps.sync.services.sync_job_service import sync_job_service


@shared_task(
    soft_time_limit=3600,
    time_limit=3900,
)
def sync_calendar_task(
    sync_subject_details: bool = True,
    job_id: str | None = None,
):
    lease_owner = f"celery:{current_task.request.id}"
    if job_id and not sync_job_service.claim(
        job_id=job_id,
        lease_owner=lease_owner,
        lease_seconds=3900,
    ):
        return {"skipped": True, "reason": "job already claimed"}
    try:
        return calendar_sync_service.sync_calendar(
            sync_subject_details=sync_subject_details,
            job_id=job_id,
        )
    except Exception as exc:
        sync_job_service.mark_failed(
            job_id=job_id,
            error=exc,
            lease_owner=lease_owner,
        )
        raise
