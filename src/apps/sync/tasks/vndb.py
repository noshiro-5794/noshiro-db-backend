from celery import current_task, shared_task

from apps.sync.services.sync_job_service import sync_job_service
from apps.sync.services.vndb_service import vndb_import_service


@shared_task(soft_time_limit=900, time_limit=960)
def import_vndb_work_task(
    vndb_id: str,
    *,
    include_related: bool = True,
    job_id: str | None = None,
) -> dict:
    lease_owner = f"celery:{current_task.request.id}"
    if job_id and not sync_job_service.claim(
        job_id=job_id,
        lease_owner=lease_owner,
        lease_seconds=960,
    ):
        return {"skipped": True, "reason": "job already claimed"}
    sync_job_service.mark_running(
        job_id=job_id,
        total_count=1,
        current_label=f"Importing VNDB {vndb_id}",
        lease_owner=lease_owner,
    )
    try:
        entity = vndb_import_service.import_work(
            vndb_id=vndb_id,
            include_related=include_related,
        )
        result = {
            "entity_id": str(entity.id),
            "provider": "vndb",
            "external_id": vndb_id,
        }
        sync_job_service.advance(
            job_id=job_id,
            processed=1,
            synced=1,
            current_label=f"Imported VNDB {vndb_id}",
            lease_owner=lease_owner,
        )
        sync_job_service.mark_succeeded(
            job_id=job_id,
            result=result,
            lease_owner=lease_owner,
        )
        return result
    except Exception as exc:
        sync_job_service.mark_failed(
            job_id=job_id,
            error=exc,
            lease_owner=lease_owner,
        )
        raise
