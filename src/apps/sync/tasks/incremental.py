from celery import shared_task

from apps.sync.services.incremental_sync_service import incremental_sync_service
from apps.sync.services.sync_job_service import sync_job_service


@shared_task(
    soft_time_limit=3600,
    time_limit=3900,
)
def run_incremental_sync_task(
    task_name: str | None = None,
    batch_size: int | None = None,
    job_id: str | None = None,
):
    try:
        if task_name:
            result = incremental_sync_service.sync_task(
                task_name=task_name,
                batch_size=batch_size,
                job_id=job_id,
            )
        else:
            result = incremental_sync_service.sync_all(
                batch_size=batch_size,
                job_id=job_id,
            )
        sync_job_service.mark_succeeded(
            job_id=job_id,
            result=result,
            current_label="Incremental sync completed",
        )
        return result
    except Exception as exc:
        sync_job_service.mark_failed(job_id=job_id, error=exc)
        raise
