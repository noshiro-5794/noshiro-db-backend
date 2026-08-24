from apps.index.models import ProviderRepresentation, SourceRecord
from apps.sync.providers.bangumi import BANGUMI_SUBJECT_NAMESPACE
from apps.sync.services.character_service import character_service
from apps.sync.services.episode_service import episode_service
from apps.sync.services.relation_service import relation_service
from apps.sync.services.staff_service import staff_service
from apps.sync.services.subject_service import subject_service
from apps.sync.tasks.base import BaseSyncTask


def _has_bangumi_subject(bangumi_id: int) -> bool:
    external_id = str(bangumi_id)
    return ProviderRepresentation.objects.filter(
        provider_record__namespace__provider__slug=BANGUMI_SUBJECT_NAMESPACE.source.slug,
        provider_record__namespace__slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        provider_record__external_id=external_id,
        provider_record__status=SourceRecord.Status.ACTIVE,
        is_active=True,
    ).exists()


class FullSubjectSyncTask(BaseSyncTask):
    TASK_NAME = "full_subject"

    def run_task(self):
        self.run(self.sync_one, 1, 640000)

    def sync_one(self, bangumi_id: int):
        subject_service.upsert_subject(bangumi_id)


class FullEpisodeSyncTask(BaseSyncTask):
    TASK_NAME = "full_episode"

    def run_task(self):
        self.run(self.sync_one, 1, 640000)

    def sync_one(self, bangumi_id: int):
        if not _has_bangumi_subject(bangumi_id):
            return

        episode_service.sync_subject_episodes(bangumi_id)


class FullSubjRelSyncTask(BaseSyncTask):
    TASK_NAME = "full_subject_subject_relation"

    def run_task(self):
        self.run(self.sync_one, 1, 640000)

    def sync_one(self, bangumi_id: int):
        if not _has_bangumi_subject(bangumi_id):
            return

        relation_service.upsert_subject_relation(bangumi_id)


class FullStfRelSyncTask(BaseSyncTask):
    TASK_NAME = "full_subject_staff_relation"

    def run_task(self):
        self.run(self.sync_one, 1, 640000)

    def sync_one(self, bangumi_id: int):
        if not _has_bangumi_subject(bangumi_id):
            return

        relation_service.upsert_staff_relation(bangumi_id)


class FullCharRelSyncTask(BaseSyncTask):
    TASK_NAME = "full_subject_character_relation"

    def run_task(self):
        self.run(self.sync_one, 1, 640000)

    def sync_one(self, bangumi_id: int):
        if not _has_bangumi_subject(bangumi_id):
            return

        relation_service.upsert_character_relation(bangumi_id)


class FullCharacterSyncTask(BaseSyncTask):
    TASK_NAME = "full_character"

    def run_task(self):
        self.run(self.sync_one, 1, 220000)

    def sync_one(self, bangumi_id: int):
        character_service.upsert_character(bangumi_id)


class FullStaffSyncTask(BaseSyncTask):
    TASK_NAME = "full_staff"

    def run_task(self):
        self.run(self.sync_one, 1, 100000)

    def sync_one(self, bangumi_id: int):
        staff_service.upsert_staff(bangumi_id)
