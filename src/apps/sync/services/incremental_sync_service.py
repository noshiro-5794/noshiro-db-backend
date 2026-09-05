import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import F, IntegerField, Max
from django.db.models.functions import Cast
from django.utils import timezone

from apps.index.models import (
    ProviderRepresentation,
    SourceRecord,
)
from apps.sync.exceptions import SyncTaskAlreadyRunning
from apps.sync.models import SyncError, SyncState
from apps.sync.providers.bangumi import (
    BANGUMI_CHARACTER_NAMESPACE,
    BANGUMI_PERSON_NAMESPACE,
    BANGUMI_SUBJECT_NAMESPACE,
    BangumiAPIError,
)
from apps.sync.services.character_service import character_service
from apps.sync.services.episode_service import episode_service
from apps.sync.services.relation_service import relation_service
from apps.sync.services.staff_service import staff_service
from apps.sync.services.subject_service import subject_service
from apps.sync.services.sync_job_service import sync_job_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncrementalTaskConfig:
    task_name: str
    full_task_name: str
    handler_name: str
    cursor_source: str
    requires_subject: bool = False


class IncrementalSyncService:
    SHARD = "main"
    TASKS = {
        "incremental_subject": IncrementalTaskConfig(
            task_name="incremental_subject",
            full_task_name="full_subject",
            handler_name="_sync_subject",
            cursor_source="subject",
        ),
        "incremental_episode": IncrementalTaskConfig(
            task_name="incremental_episode",
            full_task_name="full_episode",
            handler_name="_sync_episode",
            cursor_source="subject",
            requires_subject=True,
        ),
        "incremental_subject_subject_relation": IncrementalTaskConfig(
            task_name="incremental_subject_subject_relation",
            full_task_name="full_subject_subject_relation",
            handler_name="_sync_subject_relation",
            cursor_source="subject",
            requires_subject=True,
        ),
        "incremental_subject_staff_relation": IncrementalTaskConfig(
            task_name="incremental_subject_staff_relation",
            full_task_name="full_subject_staff_relation",
            handler_name="_sync_staff_relation",
            cursor_source="subject",
            requires_subject=True,
        ),
        "incremental_subject_character_relation": IncrementalTaskConfig(
            task_name="incremental_subject_character_relation",
            full_task_name="full_subject_character_relation",
            handler_name="_sync_character_relation",
            cursor_source="subject",
            requires_subject=True,
        ),
        "incremental_character": IncrementalTaskConfig(
            task_name="incremental_character",
            full_task_name="full_character",
            handler_name="_sync_character",
            cursor_source="character",
        ),
        "incremental_staff": IncrementalTaskConfig(
            task_name="incremental_staff",
            full_task_name="full_staff",
            handler_name="_sync_staff",
            cursor_source="staff",
        ),
    }

    @classmethod
    def get_status(cls) -> dict:
        existing_states = {
            state.task_name: state
            for state in SyncState.objects.filter(
                task_name__in=list(cls.TASKS.keys()),
                shard=cls.SHARD,
            )
        }
        states = []
        for config in cls.TASKS.values():
            state = existing_states.get(config.task_name)
            if state is None:
                state = cls._get_or_create_state(config)
            states.append(cls._serialize_state(state))
        return {"tasks": states}

    @classmethod
    def unlock_running(cls, *, task_name: str | None = None) -> dict:
        task_names = [task_name] if task_name else list(cls.TASKS.keys())
        updated = []
        for name in task_names:
            config = cls._get_config(name)
            cls._get_or_create_state(config)
            changed = SyncState.objects.filter(
                task_name=name,
                shard=cls.SHARD,
                status=SyncState.Status.RUNNING,
            ).update(
                status=SyncState.Status.FAILED,
                fail_count=F("fail_count") + 1,
            )
            if changed:
                updated.append(name)
        return {"unlocked": updated}

    @classmethod
    def sync_all(
        cls,
        *,
        batch_size: int | None = None,
        job_id: str | None = None,
        verbose: bool = False,
    ) -> dict:
        effective_batch_size = (
            batch_size or settings.SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE
        )
        sync_job_service.mark_running(
            job_id=job_id,
            total_count=len(cls.TASKS) * max(1, int(effective_batch_size)),
            current_label="Starting incremental sync",
        )
        return {
            "results": [
                cls.sync_task(
                    task_name=task_name,
                    batch_size=effective_batch_size,
                    job_id=job_id,
                    reset_job_total=False,
                    verbose=verbose,
                )
                for task_name in cls.TASKS
            ]
        }

    @classmethod
    def sync_task(
        cls,
        *,
        task_name: str,
        batch_size: int | None = None,
        job_id: str | None = None,
        reset_job_total: bool = True,
        verbose: bool = False,
    ) -> dict:
        config = cls._get_config(task_name)
        batch_size = batch_size or settings.SYNC_INCREMENTAL_SUBJECT_BATCH_SIZE
        batch_size = max(1, int(batch_size))
        sync_job_service.mark_running(
            job_id=job_id,
            total_count=batch_size if reset_job_total else None,
            current_label=f"Starting {config.task_name}",
        )
        start_id, end_id = cls._start_window(config, batch_size=batch_size)
        if verbose:
            logger.info(
                "Incremental sync window started",
                extra={
                    "task_name": config.task_name,
                    "start_id": start_id,
                    "end_id": end_id,
                },
            )

        result = {
            "task_name": config.task_name,
            "shard": cls.SHARD,
            "start_id": start_id,
            "end_id": end_id,
            "processed_count": 0,
            "synced_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
        }
        consecutive_errors = 0
        consecutive_skips = 0
        last_synced_id = start_id - 1

        try:
            for bangumi_id in range(start_id, end_id + 1):
                outcome = cls._sync_one(config=config, bangumi_id=bangumi_id)
                if verbose:
                    logger.info(
                        "Incremental sync entity processed",
                        extra={
                            "task_name": config.task_name,
                            "entity_id": bangumi_id,
                            "outcome": outcome,
                        },
                    )
                result["processed_count"] += 1
                result[f"{outcome}_count"] += 1
                sync_job_service.advance(
                    job_id=job_id,
                    synced=1 if outcome == "synced" else 0,
                    skipped=1 if outcome == "skipped" else 0,
                    failed=1 if outcome == "failed" else 0,
                    current_label=f"{config.task_name}: {bangumi_id} {outcome}",
                )

                if outcome == "failed":
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0
                    if outcome == "synced":
                        consecutive_skips = 0
                        last_synced_id = bangumi_id
                    else:
                        consecutive_skips += 1

                if consecutive_skips >= settings.SYNC_INCREMENTAL_MAX_CONSECUTIVE_SKIPS:
                    result["frontier_reached"] = True
                    cls._finish_window(
                        task_name=config.task_name,
                        current_id=last_synced_id,
                    )
                    if verbose:
                        logger.info(
                            "Incremental sync frontier reached",
                            extra={
                                "task_name": config.task_name,
                                "current_id": last_synced_id,
                            },
                        )
                    return result

                if (
                    consecutive_errors
                    >= settings.SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS
                ):
                    raise RuntimeError("Too many consecutive incremental sync errors.")

                if result["processed_count"] % 20 == 0:
                    cls._record_progress(
                        task_name=config.task_name,
                        current_id=last_synced_id,
                    )

            cls._finish_window(task_name=config.task_name, current_id=end_id)
            if verbose:
                logger.info(
                    "Incremental sync window completed",
                    extra={"task_name": config.task_name, "end_id": end_id},
                )
            return result
        except Exception:
            cls._fail_window(task_name=config.task_name, current_id=last_synced_id)
            raise

    @classmethod
    @transaction.atomic
    def _start_window(
        cls,
        config: IncrementalTaskConfig,
        *,
        batch_size: int,
    ) -> tuple[int, int]:
        state = cls._get_or_create_state_for_update(config)
        if state.status == SyncState.Status.RUNNING:
            raise SyncTaskAlreadyRunning()

        start_id = state.current_id + 1
        end_id = state.current_id + batch_size
        state.end_id = end_id
        state.status = SyncState.Status.RUNNING
        state.save(update_fields=["end_id", "status", "updated_at"])
        return start_id, end_id

    @classmethod
    def _sync_one(cls, *, config: IncrementalTaskConfig, bangumi_id: int) -> str:
        if config.requires_subject and not cls._subject_exists(bangumi_id):
            return "skipped"

        try:
            handler = getattr(cls, config.handler_name)
            handler(bangumi_id)
            return "synced"
        except BangumiAPIError as exc:
            if exc.is_not_found:
                return "skipped"
            logger.warning(
                "Incremental sync provider request failed",
                extra={"task_name": config.task_name, "entity_id": bangumi_id},
                exc_info=True,
            )
            cls._record_error(task_name=config.task_name, bangumi_id=bangumi_id)
            return "failed"
        except Exception:
            logger.exception(
                "Incremental sync entity failed",
                extra={"task_name": config.task_name, "entity_id": bangumi_id},
            )
            cls._record_error(task_name=config.task_name, bangumi_id=bangumi_id)
            return "failed"

    @staticmethod
    def _subject_exists(bangumi_id: int) -> bool:
        external_id = str(bangumi_id)
        return ProviderRepresentation.objects.filter(
            provider_record__namespace__provider__slug=(
                BANGUMI_SUBJECT_NAMESPACE.source.slug
            ),
            provider_record__namespace__slug=BANGUMI_SUBJECT_NAMESPACE.slug,
            provider_record__external_id=external_id,
            provider_record__status=SourceRecord.Status.ACTIVE,
            is_active=True,
        ).exists()

    @staticmethod
    def _sync_subject(bangumi_id: int) -> None:
        subject_service.upsert_subject(bangumi_id)

    @staticmethod
    def _sync_episode(bangumi_id: int) -> None:
        episode_service.sync_subject_episodes(bangumi_id)

    @staticmethod
    def _sync_subject_relation(bangumi_id: int) -> None:
        relation_service.upsert_subject_relation(bangumi_id)

    @staticmethod
    def _sync_staff_relation(bangumi_id: int) -> None:
        relation_service.upsert_staff_relation(bangumi_id)

    @staticmethod
    def _sync_character_relation(bangumi_id: int) -> None:
        relation_service.upsert_character_relation(bangumi_id)

    @staticmethod
    def _sync_character(bangumi_id: int) -> None:
        character_service.upsert_character(bangumi_id)

    @staticmethod
    def _sync_staff(bangumi_id: int) -> None:
        staff_service.upsert_staff(bangumi_id)

    @classmethod
    def _record_error(cls, *, task_name: str, bangumi_id: int) -> None:
        error, created = SyncError.objects.get_or_create(
            task_name=task_name,
            entity_id=bangumi_id,
        )
        if not created:
            SyncError.objects.filter(pk=error.pk).update(
                retry_count=F("retry_count") + 1,
            )

    @classmethod
    def _record_progress(cls, *, task_name: str, current_id: int) -> None:
        SyncState.objects.filter(task_name=task_name, shard=cls.SHARD).update(
            current_id=current_id,
            updated_at=timezone.now(),
        )

    @classmethod
    def _finish_window(cls, *, task_name: str, current_id: int) -> None:
        SyncState.objects.filter(task_name=task_name, shard=cls.SHARD).update(
            current_id=current_id,
            status=SyncState.Status.FINISHED,
            updated_at=timezone.now(),
        )

    @classmethod
    def _fail_window(cls, *, task_name: str, current_id: int) -> None:
        cls._get_or_create_state(cls._get_config(task_name))
        SyncState.objects.filter(task_name=task_name, shard=cls.SHARD).update(
            current_id=current_id,
            status=SyncState.Status.FAILED,
            fail_count=F("fail_count") + 1,
            updated_at=timezone.now(),
        )

    @classmethod
    def _get_config(cls, task_name: str) -> IncrementalTaskConfig:
        try:
            return cls.TASKS[task_name]
        except KeyError as exc:
            raise ValueError(f"Unknown incremental sync task: {task_name}") from exc

    @classmethod
    def _get_or_create_state(cls, config: IncrementalTaskConfig) -> SyncState:
        state = SyncState.objects.filter(
            task_name=config.task_name,
            shard=cls.SHARD,
        ).first()
        if state:
            return state

        initial_current_id = cls._get_initial_current_id(config)
        state, _ = SyncState.objects.get_or_create(
            task_name=config.task_name,
            shard=cls.SHARD,
            defaults={
                "current_id": initial_current_id,
                "end_id": initial_current_id,
                "status": SyncState.Status.IDLE,
            },
        )
        return state

    @classmethod
    def _get_or_create_state_for_update(
        cls,
        config: IncrementalTaskConfig,
    ) -> SyncState:
        cls._get_or_create_state(config)
        return SyncState.objects.select_for_update().get(
            task_name=config.task_name,
            shard=cls.SHARD,
        )

    @staticmethod
    def _get_initial_current_id(config: IncrementalTaskConfig) -> int:
        namespace_spec = {
            "subject": BANGUMI_SUBJECT_NAMESPACE,
            "character": BANGUMI_CHARACTER_NAMESPACE,
            "staff": BANGUMI_PERSON_NAMESPACE,
        }[config.cursor_source]
        numeric_external_id = Cast("external_id", IntegerField())
        source_value = (
            SourceRecord.objects.filter(
                namespace__provider__slug=namespace_spec.source.slug,
                namespace__slug=namespace_spec.slug,
                status=SourceRecord.Status.ACTIVE,
                external_id__regex=r"^[0-9]+$",
            )
            .annotate(numeric_external_id=numeric_external_id)
            .aggregate(max_external_id=Max("numeric_external_id"))["max_external_id"]
        )
        if source_value:
            return source_value

        fallback = (
            SyncState.objects.filter(
                task_name=config.full_task_name,
                status=SyncState.Status.FINISHED,
            )
            .aggregate(max_end_id=Max("end_id"))
            .get("max_end_id")
        )
        return fallback or 0

    @staticmethod
    def _serialize_state(state: SyncState) -> dict:
        return {
            "task_name": state.task_name,
            "shard": state.shard,
            "current_id": state.current_id,
            "end_id": state.end_id,
            "status": state.status,
            "fail_count": state.fail_count,
            "updated_at": state.updated_at,
        }


incremental_sync_service = IncrementalSyncService()
