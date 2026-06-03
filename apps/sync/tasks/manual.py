from celery import shared_task

from apps.sync.services.manual_sync_service import manual_subject_sync_service


class ManualSyncTask:

    @staticmethod
    def sync_subject(bangumi_id: int):
        return manual_subject_sync_service.sync_by_bangumi_id(
            bangumi_id=bangumi_id,
        )

    @staticmethod
    def sync_subject_by_uuid(subject_id: str):
        return manual_subject_sync_service.sync_by_uuid(
            subject_id=subject_id,
        )


@shared_task(
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def sync_subject_by_uuid_task(self, subject_id: str):
    return ManualSyncTask.sync_subject_by_uuid(subject_id)


@shared_task(
    bind=True,
    soft_time_limit=300,
    time_limit=360,
)
def sync_subject_by_bangumi_id_task(self, bangumi_id: int):
    return ManualSyncTask.sync_subject(bangumi_id)
