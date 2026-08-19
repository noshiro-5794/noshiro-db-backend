import json
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from django.db import connection, models, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.community.models import Activity, CommunityPost
from apps.index.models import (
    Appearance,
    Character,
    Credit,
    DataMigrationCheckpoint,
    DataMigrationRun,
    Entity,
    EntityDescription,
    EntityName,
    EntityRelation,
    EntityRelationEvidence,
    Episode,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
    Staff,
    Subject,
    SubjectCharacterActorRelation,
    SubjectCharacterRelation,
    SubjectStaffRelation,
    SubjectSubjectRelation,
    VoicePerformance,
)
from apps.index.services import knowledge_ingestion_service
from apps.users.models import UserSubject


@dataclass(frozen=True, slots=True)
class BackfillStage:
    name: str
    model: type[models.Model]
    processor: str


STAGES = (
    BackfillStage("subjects", Subject, "_process_subject"),
    BackfillStage("characters", Character, "_process_character"),
    BackfillStage("contributors", Staff, "_process_contributor"),
    BackfillStage("episodes", Episode, "_process_episode"),
    BackfillStage("work_relations", SubjectSubjectRelation, "_process_work_relation"),
    BackfillStage("credits", SubjectStaffRelation, "_process_credit"),
    BackfillStage("appearances", SubjectCharacterRelation, "_process_appearance"),
    BackfillStage(
        "voice_performances",
        SubjectCharacterActorRelation,
        "_process_voice_performance",
    ),
    BackfillStage("library_entries", UserSubject, "_process_library_entry"),
    BackfillStage("community_posts", CommunityPost, "_process_community_post"),
    BackfillStage("community_activities", Activity, "_process_community_activity"),
)


class KnowledgeGraphBackfillError(RuntimeError):
    """Raised when a legacy knowledge graph backfill cannot be completed."""


class KnowledgeGraphBackfillService:
    COMMAND_NAME = "backfill_knowledge_graph"
    VERSION = "2"
    DEFAULT_BATCH_SIZE = 500
    UUID_NAMESPACE = uuid.UUID("1e6aface-b51d-4cf9-b37a-7dd12beb2e2e")
    LOCK_KEY = "noshiro:data-migration:backfill-knowledge-graph"

    def __init__(self, *, write: Callable[[str], None] | None = None) -> None:
        self._write = write or (lambda _message: None)

    def run(
        self,
        *,
        batch_size: int | None = None,
        resume_id: uuid.UUID | None = None,
        status_id: uuid.UUID | None = None,
        max_batches: int | None = None,
        dry_run: bool = False,
    ) -> None:
        if batch_size is not None and batch_size < 1:
            raise KnowledgeGraphBackfillError("--batch-size must be greater than zero.")
        if max_batches is not None and max_batches < 1:
            raise KnowledgeGraphBackfillError(
                "--max-batches must be greater than zero."
            )
        if status_id and any((resume_id, dry_run, batch_size, max_batches)):
            raise KnowledgeGraphBackfillError(
                "--status cannot be combined with execution options."
            )
        if resume_id and dry_run:
            raise KnowledgeGraphBackfillError(
                "--resume and --dry-run cannot be combined."
            )

        if status_id:
            self._print_status(status_id)
            return

        self._preflight()
        if dry_run:
            self._print_dry_run()
            return

        with self._migration_lock():
            run = self._load_or_create_run(
                resume_id=resume_id,
                batch_size=batch_size,
            )
            self._write(f"run_id={run.id}")
            try:
                self._execute(run=run, max_batches=max_batches)
            except KeyboardInterrupt:
                self._set_run_status(run, DataMigrationRun.Status.PAUSED)
                raise
            except Exception as exc:
                self._set_run_status(
                    run,
                    DataMigrationRun.Status.FAILED,
                    error=f"{type(exc).__name__}: {exc}"[:4000],
                )
                raise KnowledgeGraphBackfillError(
                    f"Backfill failed; resume run {run.id}: {exc}"
                ) from exc

    def _preflight(self) -> None:
        expected_sources = (
            (Subject, "bangumi_subject", "subjects"),
            (Character, "bangumi_character", "characters"),
            (Staff, "bangumi_persons", "contributors"),
            (Episode, "bangumi_episode", "episodes"),
        )
        for model, expected_source, label in expected_sources:
            unknown = list(
                model.objects.exclude(info_source=expected_source)
                .values_list("info_source", flat=True)
                .distinct()[:20]
            )
            if unknown:
                raise KnowledgeGraphBackfillError(
                    f"{label} contain unsupported legacy sources: {unknown}"
                )
            if model.objects.filter(id_source="").exists():
                raise KnowledgeGraphBackfillError(
                    f"{label} contain an empty id_source."
                )

    def _print_dry_run(self) -> None:
        summary = {
            stage.name: {
                "rows": stage.model.objects.count(),
                "upper_bound": self._upper_bound(stage.model),
            }
            for stage in STAGES
        }
        self._write(json.dumps(summary, indent=2, sort_keys=True))

    def _print_status(self, run_id: uuid.UUID) -> None:
        try:
            run = DataMigrationRun.objects.get(pk=run_id, command=self.COMMAND_NAME)
        except DataMigrationRun.DoesNotExist as exc:
            raise KnowledgeGraphBackfillError(
                f"Backfill run {run_id} does not exist."
            ) from exc
        payload = {
            "run_id": str(run.id),
            "version": run.version,
            "status": run.status,
            "batch_size": run.batch_size,
            "error": run.error,
            "checkpoints": [
                {
                    "stage": checkpoint.stage,
                    "cursor": checkpoint.cursor or None,
                    "upper_bound": checkpoint.upper_bound or None,
                    "processed_count": checkpoint.processed_count,
                    "is_complete": checkpoint.is_complete,
                }
                for checkpoint in run.checkpoints.order_by("id")
            ],
        }
        self._write(json.dumps(payload, indent=2, sort_keys=True))

    @contextmanager
    def _migration_lock(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))",
                [self.LOCK_KEY],
            )
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise KnowledgeGraphBackfillError(
                "Another knowledge graph backfill is already running."
            )
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    [self.LOCK_KEY],
                )

    def _load_or_create_run(
        self,
        *,
        resume_id: uuid.UUID | None,
        batch_size: int | None,
    ) -> DataMigrationRun:
        if resume_id is None:
            return self._create_run(batch_size or self.DEFAULT_BATCH_SIZE)

        try:
            run = DataMigrationRun.objects.get(pk=resume_id, command=self.COMMAND_NAME)
        except DataMigrationRun.DoesNotExist as exc:
            raise KnowledgeGraphBackfillError(
                f"Backfill run {resume_id} does not exist."
            ) from exc
        if run.version != self.VERSION:
            raise KnowledgeGraphBackfillError(
                f"Run {run.id} uses command version {run.version}; expected {self.VERSION}."
            )
        if run.status == DataMigrationRun.Status.SUCCEEDED:
            raise KnowledgeGraphBackfillError(
                f"Backfill run {run.id} has already succeeded."
            )
        if set(run.checkpoints.values_list("stage", flat=True)) != {
            stage.name for stage in STAGES
        }:
            raise KnowledgeGraphBackfillError(
                f"Backfill run {run.id} has an incompatible stage set."
            )

        run.batch_size = batch_size or run.batch_size
        run.status = DataMigrationRun.Status.RUNNING
        run.error = ""
        run.finished_at = None
        run.save(
            update_fields=[
                "batch_size",
                "status",
                "error",
                "finished_at",
                "updated_at",
            ]
        )
        return run

    @transaction.atomic
    def _create_run(self, batch_size: int) -> DataMigrationRun:
        now = timezone.now()
        run = DataMigrationRun.objects.create(
            command=self.COMMAND_NAME,
            version=self.VERSION,
            status=DataMigrationRun.Status.RUNNING,
            batch_size=batch_size,
            parameters={"stages": [stage.name for stage in STAGES]},
            started_at=now,
        )
        checkpoints = []
        for stage in STAGES:
            upper_bound = self._upper_bound(stage.model)
            checkpoints.append(
                DataMigrationCheckpoint(
                    run=run,
                    stage=stage.name,
                    upper_bound=upper_bound,
                    is_complete=not upper_bound,
                )
            )
        DataMigrationCheckpoint.objects.bulk_create(checkpoints)
        return run

    @staticmethod
    def _upper_bound(model: type[models.Model]) -> str:
        value = model.objects.order_by("-pk").values_list("pk", flat=True).first()
        return str(value) if value is not None else ""

    def _execute(self, *, run: DataMigrationRun, max_batches: int | None) -> None:
        committed_batches = 0
        for stage in STAGES:
            while True:
                processed = self._process_next_batch(run=run, stage=stage)
                if processed == 0:
                    break
                committed_batches += 1
                if (
                    max_batches
                    and committed_batches >= max_batches
                    and run.checkpoints.filter(is_complete=False).exists()
                ):
                    self._set_run_status(run, DataMigrationRun.Status.PAUSED)
                    self._write(
                        f"paused run_id={run.id} committed_batches={committed_batches}"
                    )
                    return
        self._set_run_status(run, DataMigrationRun.Status.SUCCEEDED)
        self._write(f"completed run_id={run.id}")

    @transaction.atomic
    def _process_next_batch(
        self,
        *,
        run: DataMigrationRun,
        stage: BackfillStage,
    ) -> int:
        checkpoint = DataMigrationCheckpoint.objects.select_for_update().get(
            run=run,
            stage=stage.name,
        )
        if checkpoint.is_complete:
            return 0

        queryset = stage.model.objects.order_by("pk")
        upper_bound = stage.model._meta.pk.to_python(checkpoint.upper_bound)
        queryset = queryset.filter(pk__lte=upper_bound)
        if checkpoint.cursor:
            cursor = stage.model._meta.pk.to_python(checkpoint.cursor)
            queryset = queryset.filter(pk__gt=cursor)
        primary_keys = list(queryset.values_list("pk", flat=True)[: run.batch_size])
        if not primary_keys:
            checkpoint.is_complete = True
            checkpoint.save(update_fields=["is_complete", "updated_at"])
            return 0

        processor = getattr(self, stage.processor)
        for primary_key in primary_keys:
            processor(primary_key)

        checkpoint.cursor = str(primary_keys[-1])
        checkpoint.processed_count += len(primary_keys)
        checkpoint.is_complete = primary_keys[-1] == upper_bound
        checkpoint.save(
            update_fields=[
                "cursor",
                "processed_count",
                "is_complete",
                "updated_at",
            ]
        )
        self._write(
            f"stage={stage.name} processed={checkpoint.processed_count} "
            f"cursor={checkpoint.cursor} complete={checkpoint.is_complete}"
        )
        return len(primary_keys)

    @staticmethod
    def _set_run_status(
        run: DataMigrationRun,
        status: str,
        *,
        error: str = "",
    ) -> None:
        run.status = status
        run.error = error
        run.finished_at = (
            timezone.now()
            if status
            in {DataMigrationRun.Status.FAILED, DataMigrationRun.Status.SUCCEEDED}
            else None
        )
        run.save(update_fields=["status", "error", "finished_at", "updated_at"])

    @staticmethod
    def _provider() -> Provider:
        provider, _ = Provider.objects.get_or_create(
            slug="bangumi",
            defaults={
                "name": "Bangumi",
                "base_url": "https://api.bgm.tv",
                "terms_url": "https://bangumi.github.io/api/",
                "attribution_url": "https://bgm.tv",
            },
        )
        return provider

    def _record(
        self,
        *,
        namespace_slug: str,
        resource_type: str,
        external_id: str,
    ) -> ProviderRecord:
        namespace, _ = ProviderNamespace.objects.get_or_create(
            provider=self._provider(),
            slug=namespace_slug,
            defaults={"resource_type": resource_type},
        )
        record, _ = ProviderRecord.objects.get_or_create(
            namespace=namespace,
            external_id=external_id,
            defaults={
                "origin": ProviderRecord.Origin.LEGACY_PROJECTION,
                "canonical_url": self._canonical_url(namespace_slug, external_id),
            },
        )
        return record

    @staticmethod
    def _canonical_url(namespace_slug: str, external_id: str) -> str:
        path = {
            "subject": "subject",
            "episode": "ep",
            "person": "person",
            "character": "character",
        }.get(namespace_slug)
        return f"https://bgm.tv/{path}/{external_id}" if path else ""

    def _subject_record(self, subject: Subject) -> ProviderRecord:
        return self._record(
            namespace_slug="subject",
            resource_type=ProviderNamespace.ResourceType.SUBJECT,
            external_id=subject.id_source,
        )

    def _relation_observation(
        self,
        *,
        subject: Subject,
        schema_name: str,
        mapper: str,
        payload: dict[str, Any],
    ):
        return knowledge_ingestion_service.record_observation(
            provider_record=self._subject_record(subject),
            mapper=mapper,
            mapper_version=f"legacy-{mapper}-v1",
            normalized_data={"legacy": True, **payload},
            schema_name=schema_name,
            schema_version="1",
        )

    def _process_subject(self, primary_key: uuid.UUID) -> None:
        subject = Subject.objects.get(pk=primary_key)
        knowledge_ingestion_service.project_subject(
            subject=subject,
            provider_record=self._subject_record(subject),
            normalized_data={
                "legacy": True,
                "title": subject.title,
                "title_cn": subject.title_cn,
                "subject_type": subject.subject_type,
                "date": subject.date.isoformat() if subject.date else None,
                "platform": subject.platform,
                "description": subject.description,
                "nsfw": subject.nsfw,
                "infobox": subject.infobox,
                "tags": subject.tags,
            },
            mapper_version="legacy-subject-v1",
            representation_method=ProviderRepresentation.Method.LEGACY,
        )

    def _process_character(self, primary_key: int) -> None:
        character = Character.objects.get(pk=primary_key)
        record = self._record(
            namespace_slug="character",
            resource_type=ProviderNamespace.ResourceType.CHARACTER,
            external_id=character.id_source,
        )
        knowledge_ingestion_service.project_character(
            character=character,
            provider_record=record,
            normalized_data={
                "legacy": True,
                "name": character.name,
                "description": character.description,
                "gender": character.gender,
                "birth": character.birth,
                "blood_type": character.blood_type,
                "infobox": character.infobox,
            },
            mapper="bangumi.character",
            mapper_version="legacy-character-v1",
            representation_method=ProviderRepresentation.Method.LEGACY,
        )

    def _process_contributor(self, primary_key: int) -> None:
        staff = Staff.objects.get(pk=primary_key)
        record = self._record(
            namespace_slug="person",
            resource_type=ProviderNamespace.ResourceType.PERSON,
            external_id=staff.id_source,
        )
        knowledge_ingestion_service.project_staff(
            staff=staff,
            provider_record=record,
            normalized_data={
                "legacy": True,
                "name": staff.name,
                "description": staff.description,
                "gender": staff.gender,
                "birth": staff.birth,
                "career": staff.career,
                "infobox": staff.infobox,
            },
            mapper="bangumi.person",
            mapper_version="legacy-person-v1",
            representation_method=ProviderRepresentation.Method.LEGACY,
        )

    def _process_episode(self, primary_key: int) -> None:
        episode = Episode.objects.select_related("subject").get(pk=primary_key)
        parent = Entity.objects.get(pk=episode.subject_id)
        if episode.entity_id is None:
            entity, created = Entity.objects.get_or_create(
                id=uuid.uuid5(self.UUID_NAMESPACE, f"episode:{episode.pk}"),
                defaults={
                    "kind": Entity.Kind.EPISODE,
                    "audience": parent.audience,
                },
            )
            if not created and entity.kind != Entity.Kind.EPISODE:
                raise ValueError(
                    f"Episode {episode.pk} entity UUID collides with {entity.kind}."
                )
            episode.entity = entity
            episode.save(update_fields=["entity", "updated_at"])
        if (
            parent.audience == Entity.Audience.ADULT
            and episode.entity.audience != Entity.Audience.ADULT
        ):
            episode.entity.audience = Entity.Audience.ADULT
            episode.entity.save(update_fields=["audience", "updated_at"])
        record = self._record(
            namespace_slug="episode",
            resource_type=ProviderNamespace.ResourceType.EPISODE,
            external_id=episode.id_source,
        )
        observation = knowledge_ingestion_service.record_observation(
            provider_record=record,
            mapper="bangumi.episode",
            mapper_version="legacy-episode-v1",
            normalized_data={
                "legacy": True,
                "title": episode.title,
                "type": episode.type,
                "ep": str(episode.ep_num) if episode.ep_num is not None else None,
                "sort": str(episode.sort) if episode.sort is not None else None,
                "date": episode.date.isoformat() if episode.date else None,
                "description": episode.description,
            },
            schema_name="index.episode",
            schema_version="1",
        )
        ProviderRepresentation.objects.update_or_create(
            provider_record=record,
            entity=episode.entity,
            mapping_kind=ProviderRepresentation.MappingKind.EXACT,
            defaults={
                "method": ProviderRepresentation.Method.LEGACY,
                "confidence": 1,
                "is_active": True,
            },
        )
        if episode.title:
            EntityName.objects.get_or_create(
                entity=episode.entity,
                provider_record=record,
                observation=observation,
                text=episode.title,
                language="",
                kind=EntityName.Kind.ORIGINAL,
                defaults={"is_original": True},
            )
        if episode.description:
            EntityDescription.objects.update_or_create(
                entity=episode.entity,
                language="",
                provider_record=record,
                observation=observation,
                defaults={"text": episode.description},
            )
        relation, _ = EntityRelation.objects.get_or_create(
            from_entity_id=episode.subject_id,
            to_entity=episode.entity,
            relation_type="has-episode",
        )
        EntityRelationEvidence.objects.get_or_create(
            relation=relation,
            observation=observation,
            json_pointer="/subject",
            defaults={"raw_relation": "has-episode"},
        )

    def _process_work_relation(self, primary_key: int) -> None:
        legacy = SubjectSubjectRelation.objects.select_related("source").get(
            pk=primary_key
        )
        raw_relation = legacy.relation or "related"
        relation_type = slugify(raw_relation)[:128] or "related"
        observation = self._relation_observation(
            subject=legacy.source,
            schema_name="index.entity-relation",
            mapper="bangumi.subject-relation",
            payload={
                "target_subject_id": str(legacy.target_id),
                "relation": raw_relation,
            },
        )
        relation, _ = EntityRelation.objects.get_or_create(
            from_entity_id=legacy.source_id,
            to_entity_id=legacy.target_id,
            relation_type=relation_type,
        )
        EntityRelationEvidence.objects.get_or_create(
            relation=relation,
            observation=observation,
            json_pointer=f"/legacy_relation/{legacy.pk}",
            defaults={"raw_relation": raw_relation},
        )

    def _process_credit(self, primary_key: int) -> None:
        legacy = SubjectStaffRelation.objects.select_related("subject", "staff").get(
            pk=primary_key
        )
        if legacy.staff.contributor_id is None:
            raise ValueError(f"Staff {legacy.staff_id} has no Contributor projection.")
        observation = self._relation_observation(
            subject=legacy.subject,
            schema_name="index.credit",
            mapper="bangumi.subject-person-relation",
            payload={"staff_id": legacy.staff_id, "role": legacy.role},
        )
        Credit.objects.get_or_create(
            work_id=legacy.subject_id,
            contributor_id=legacy.staff.contributor_id,
            role=legacy.role or "staff",
            credited_as="",
            observation=observation,
        )

    def _process_appearance(self, primary_key: int) -> None:
        legacy = SubjectCharacterRelation.objects.select_related(
            "subject", "character"
        ).get(pk=primary_key)
        if legacy.character.entity_id is None:
            raise ValueError(
                f"Character {legacy.character_id} has no Entity projection."
            )
        observation = self._relation_observation(
            subject=legacy.subject,
            schema_name="index.appearance",
            mapper="bangumi.subject-character-relation",
            payload={"character_id": legacy.character_id, "role": legacy.role},
        )
        Appearance.objects.get_or_create(
            work_id=legacy.subject_id,
            character_entity_id=legacy.character.entity_id,
            role=legacy.role,
            observation=observation,
        )

    def _process_voice_performance(self, primary_key: int) -> None:
        legacy = SubjectCharacterActorRelation.objects.select_related(
            "subject", "character", "actor"
        ).get(pk=primary_key)
        if legacy.character.entity_id is None:
            raise ValueError(
                f"Character {legacy.character_id} has no Entity projection."
            )
        if legacy.actor.contributor_id is None:
            raise ValueError(f"Actor {legacy.actor_id} has no Contributor projection.")
        appearance = (
            Appearance.objects.filter(
                work_id=legacy.subject_id,
                character_entity_id=legacy.character.entity_id,
            )
            .order_by("pk")
            .first()
        )
        if appearance is None:
            raise ValueError(
                f"Character {legacy.character_id} has no appearance in {legacy.subject_id}."
            )
        observation = self._relation_observation(
            subject=legacy.subject,
            schema_name="index.voice-performance",
            mapper="bangumi.subject-character-actor-relation",
            payload={
                "character_id": legacy.character_id,
                "actor_id": legacy.actor_id,
            },
        )
        VoicePerformance.objects.get_or_create(
            appearance=appearance,
            contributor_id=legacy.actor.contributor_id,
            language="",
            observation=observation,
        )

    @staticmethod
    def _process_library_entry(primary_key: int) -> None:
        entry = UserSubject.objects.get(pk=primary_key)
        if entry.entity_id is not None:
            return
        if entry.subject_id is None:
            raise ValueError(
                f"Library entry {entry.pk} has neither Subject nor Entity."
            )
        entry.entity_id = entry.subject_id
        entry.save(update_fields=["entity"])

    @staticmethod
    def _process_community_post(primary_key: int) -> None:
        post = CommunityPost.objects.get(pk=primary_key)
        if post.entity_id is not None or post.subject_id is None:
            return
        post.entity_id = post.subject_id
        post.post_type = CommunityPost.PostType.ENTITY
        post.save(update_fields=["entity", "post_type", "updated_at"])

    @staticmethod
    def _process_community_activity(primary_key: int) -> None:
        activity = Activity.objects.select_related(
            "user_subject",
            "review__user_subject",
            "collection_item__user_subject",
            "post",
        ).get(pk=primary_key)
        if activity.entity_id is not None:
            return
        entity_id = activity.subject_id
        if entity_id is None and activity.user_subject_id:
            entity_id = activity.user_subject.entity_id
        if entity_id is None and activity.review_id:
            entity_id = activity.review.user_subject.entity_id
        if entity_id is None and activity.collection_item_id:
            entity_id = activity.collection_item.user_subject.entity_id
        if entity_id is None and activity.post_id:
            entity_id = activity.post.entity_id or activity.post.subject_id
        if entity_id is None:
            return
        activity.entity_id = entity_id
        activity.save(update_fields=["entity"])
