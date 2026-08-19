from dataclasses import dataclass
from uuid import UUID

from apps.index.models import Subject
from apps.sync.exceptions import SyncSubjectNotFound, SyncSubjectNotSupported
from apps.sync.providers.bangumi import BANGUMI_SUBJECT_NAMESPACE
from apps.sync.services.character_service import character_service
from apps.sync.services.episode_service import episode_service
from apps.sync.services.relation_service import relation_service
from apps.sync.services.source_record_service import source_identity_service
from apps.sync.services.staff_service import staff_service
from apps.sync.services.subject_service import subject_service
from apps.sync.services.sync_job_service import sync_job_service


@dataclass(frozen=True)
class ManualSubjectSyncResult:
    subject_id: str
    bangumi_id: int
    title: str
    subject_type: str
    episode_synced: bool
    staff_count: int
    character_count: int
    related_subject_count: int

    def as_dict(self) -> dict:
        return {
            "subject_id": self.subject_id,
            "bangumi_id": self.bangumi_id,
            "title": self.title,
            "subject_type": self.subject_type,
            "episode_synced": self.episode_synced,
            "staff_count": self.staff_count,
            "character_count": self.character_count,
            "related_subject_count": self.related_subject_count,
        }


class ManualSubjectSyncService:
    @staticmethod
    def sync_by_uuid(
        *, subject_id: UUID | str, job_id: UUID | str | None = None
    ) -> dict:
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist as exc:
            raise SyncSubjectNotFound() from exc

        bangumi_id = ManualSubjectSyncService.get_bangumi_subject_id(subject)
        return ManualSubjectSyncService.sync_by_bangumi_id(
            bangumi_id=bangumi_id,
            job_id=job_id,
        )

    @staticmethod
    def sync_by_bangumi_id(
        *, bangumi_id: int, job_id: UUID | str | None = None
    ) -> dict:
        sync_job_service.mark_running(
            job_id=job_id,
            total_count=3,
            current_label=f"Fetching subject {bangumi_id}",
        )
        subject = subject_service.upsert_subject(bangumi_id)
        sync_job_service.advance(
            job_id=job_id,
            synced=1,
            current_label=f"Synced subject {bangumi_id}",
        )

        episode_service.sync_subject_episodes(bangumi_id)
        sync_job_service.advance(
            job_id=job_id,
            synced=1,
            current_label=f"Synced episodes for {bangumi_id}",
        )

        relations = relation_service.sync_all_relations(bangumi_id)
        sync_job_service.advance(
            job_id=job_id,
            synced=1,
            current_label=f"Synced relations for {bangumi_id}",
        )

        staff_ids = relations["staffs"]
        character_ids = relations["characters"]
        sync_job_service.set_total(
            job_id=job_id,
            total_count=3 + len(character_ids) + len(staff_ids),
            current_label="Syncing characters and staff",
        )

        for character_id in sorted(character_ids, key=int):
            character_service.upsert_character(int(character_id))
            sync_job_service.advance(
                job_id=job_id,
                synced=1,
                current_label=f"Synced character {character_id}",
            )

        for staff_id in sorted(staff_ids, key=int):
            staff_service.upsert_staff(int(staff_id))
            sync_job_service.advance(
                job_id=job_id,
                synced=1,
                current_label=f"Synced staff {staff_id}",
            )

        result = ManualSubjectSyncResult(
            subject_id=str(subject.id),
            bangumi_id=bangumi_id,
            title=subject.title,
            subject_type=subject.subject_type,
            episode_synced=True,
            staff_count=len(staff_ids),
            character_count=len(character_ids),
            related_subject_count=len(relations["subjects"]),
        )
        data = result.as_dict()
        sync_job_service.mark_succeeded(
            job_id=job_id,
            result=data,
            current_label="Subject sync completed",
        )
        return data

    @staticmethod
    def get_bangumi_subject_id(subject: Subject) -> int:
        external_id = source_identity_service.resolve_subject_external_id(
            subject=subject,
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            legacy_source=subject_service.INFO_SOURCE,
        )
        if external_id is None:
            raise SyncSubjectNotSupported()

        try:
            return int(external_id)
        except (TypeError, ValueError) as exc:
            raise SyncSubjectNotSupported() from exc


manual_subject_sync_service = ManualSubjectSyncService()
