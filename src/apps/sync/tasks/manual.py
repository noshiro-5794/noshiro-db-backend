from celery import shared_task

from apps.sync.services.manual_sync_service import manual_subject_sync_service
from apps.sync.services.sync_job_service import sync_job_service


class ManualSyncTask:
    @staticmethod
    def sync_subject(bangumi_id: int, job_id: str | None = None):
        try:
            return manual_subject_sync_service.sync_by_bangumi_id(
                bangumi_id=bangumi_id,
                job_id=job_id,
            )
        except Exception as exc:
            sync_job_service.mark_failed(job_id=job_id, error=exc)
            raise

    @staticmethod
    def sync_subject_by_uuid(subject_id: str, job_id: str | None = None):
        try:
            return manual_subject_sync_service.sync_by_uuid(
                subject_id=subject_id,
                job_id=job_id,
            )
        except Exception as exc:
            sync_job_service.mark_failed(job_id=job_id, error=exc)
            raise


@shared_task(
    soft_time_limit=300,
    time_limit=360,
)
def sync_subject_by_uuid_task(subject_id: str, job_id: str | None = None):
    return ManualSyncTask.sync_subject_by_uuid(subject_id, job_id=job_id)


@shared_task(
    soft_time_limit=300,
    time_limit=360,
)
def sync_subject_by_bangumi_id_task(
    bangumi_id: int,
    job_id: str | None = None,
):
    return ManualSyncTask.sync_subject(bangumi_id, job_id=job_id)
