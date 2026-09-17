"""Daily refresh queue for the currently-airing board.

The calendar task only replaces the weekly on-air board (fast, low provider
load). A separate durable daily queue refreshes subject metadata and episode
air dates for every board member in bounded batches, so a whole-season anime
list never makes the daily window explode into one huge synchronous job.

Progress lives in ``SyncState`` under a per-day and per-season shard:

    shard = "airing_daily:<local-date>:<season-key>"

Workers process sorted provider records of the active board's canonical works
one batch at a time until the day shard reaches FINISHED. A new calendar date
starts a new shard; season rollover changes the season component automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.index.models import (
    AiringBoard,
    AiringBoardEntry,
    AiringEvent,
    ProviderRepresentation,
)
from apps.sync.models import SyncError, SyncState
from apps.sync.providers.bangumi import BangumiAPIError
from apps.sync.services.anilist_service import anilist_import_service
from apps.sync.services.episode_service import episode_service
from apps.sync.services.mal_service import mal_import_service
from apps.sync.services.subject_service import subject_service
from apps.sync.services.sync_job_service import sync_job_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AiringTarget:
    provider_slug: str
    external_id: str
    work_id: str


SUPPORTED_PROVIDER_SLUGS = ("bangumi", "anilist", "mal")


class AiringDailySyncService:
    TASK_NAME = "airing_daily"
    DEFAULT_SHARD = "airing"

    def board_targets(self) -> tuple[list[AiringTarget], str | None]:
        board = (
            AiringBoard.objects.filter(status=AiringBoard.Status.ACTIVE)
            .select_related("observation")
            .first()
        )
        if board is None:
            return [], board.season_key if board is not None else None
        work_ids: set[str] = set()
        if board.observation_id is not None:
            work_ids.update(
                AiringEvent.objects.filter(observation_id=board.observation_id)
                .values_list("work_id", flat=True)
                .distinct()
            )
        if (
            board.observation_id is not None
            or AiringBoardEntry.objects.filter(board=board).exists()
        ):
            work_ids.update(
                AiringBoardEntry.objects.filter(board=board).values_list(
                    "work_id", flat=True
                )
            )
        if not work_ids:
            return [], board.season_key
        representations = (
            ProviderRepresentation.objects.filter(
                entity_id__in=list(work_ids),
                provider_record__namespace__provider__slug__in=(
                    SUPPORTED_PROVIDER_SLUGS
                ),
                provider_record__status="active",
                is_active=True,
            )
            .select_related("provider_record__namespace__provider")
            .order_by("provider_record__external_id")
        )
        targets: list[AiringTarget] = []
        seen: set[str] = set()
        for representation in representations:
            provider_slug = representation.provider_record.namespace.provider.slug
            if provider_slug not in SUPPORTED_PROVIDER_SLUGS:
                continue
            external_id = representation.provider_record.external_id
            key = f"{provider_slug}:{external_id}"
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                AiringTarget(
                    provider_slug=provider_slug,
                    external_id=external_id,
                    work_id=str(representation.entity_id),
                )
            )
        return (
            sorted(
                targets,
                key=lambda item: (item.provider_slug, item.external_id),
            ),
            board.season_key,
        )

    def shard_for(
        self,
        *,
        now=None,
        season_key: str | None = None,
    ) -> str:
        local_now = timezone.localtime(now or timezone.now())
        season = (season_key or "").strip()
        suffix = season or self.DEFAULT_SHARD
        return f"{self.TASK_NAME}:{local_now.date().isoformat()}:{suffix}"

    @classmethod
    def get_status(cls, *, season_key: str | None = None) -> dict:
        shard = cls().shard_for(season_key=season_key)
        state = SyncState.objects.filter(task_name=cls.TASK_NAME, shard=shard).first()
        return {
            "task_name": cls.TASK_NAME,
            "shard": shard,
            "state": cls._serialize_state(state) if state else None,
        }

    @classmethod
    def cancel_stale_seasons(cls, *, active_season_key: str) -> int:
        """Retire daily-sync shards that belong to an older broadcast season."""
        return (
            SyncState.objects.filter(
                task_name=cls.TASK_NAME,
            )
            .exclude(
                shard__endswith=f":{active_season_key}",
            )
            .update(
                status=SyncState.Status.FINISHED,
                updated_at=timezone.now(),
            )
        )

    def sync_day(
        self,
        *,
        batch_size: int | None = None,
        job_id: str | None = None,
        verbose: bool = False,
    ) -> dict:
        targets, season_key = self.board_targets()
        shard = self.shard_for(season_key=season_key)
        batch_size = max(1, int(batch_size or settings.AIRING_DAILY_BATCH_SIZE))
        sync_job_service.mark_running(
            job_id=job_id,
            total_count=len(targets),
            current_label=f"Starting {self.TASK_NAME} ({shard})",
        )
        result = {
            "task_name": self.TASK_NAME,
            "shard": shard,
            "season_key": season_key or "",
            "target_count": len(targets),
            "processed_count": 0,
            "synced_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "remaining_count": 0,
            "completed": False,
        }
        if not targets:
            sync_job_service.mark_succeeded(
                job_id=job_id,
                result=result,
                current_label="Airing daily queue is empty",
            )
            return result

        existing = SyncState.objects.filter(
            task_name=self.TASK_NAME,
            shard=shard,
        ).first()
        if (
            existing is not None
            and existing.status == SyncState.Status.FINISHED
            and existing.current_id >= len(targets)
        ):
            result["completed"] = True
            result["remaining_count"] = 0
            sync_job_service.mark_succeeded(
                job_id=job_id,
                result=result,
                current_label="Airing daily queue already completed",
            )
            return result

        window = self._start_window(
            shard=shard,
            total_count=len(targets),
            batch_size=batch_size,
        )
        if window is None:
            state = SyncState.objects.filter(
                task_name=self.TASK_NAME, shard=shard
            ).first()
            result["remaining_count"] = (
                max(0, len(targets) - state.current_id) if state else len(targets)
            )
            result["skipped"] = True
            sync_job_service.mark_succeeded(
                job_id=job_id,
                result=result,
                current_label="Airing daily batch skipped (another is running)",
            )
            return result

        start_index, end_index = window
        consecutive_errors = 0
        try:
            for index in range(start_index, end_index + 1):
                target = targets[index]
                outcome = self._refresh_target(target)
                result["processed_count"] += 1
                result[f"{outcome}_count"] += 1
                sync_job_service.advance(
                    job_id=job_id,
                    synced=1 if outcome == "synced" else 0,
                    skipped=1 if outcome == "skipped" else 0,
                    failed=1 if outcome == "failed" else 0,
                    current_label=(
                        f"{self.TASK_NAME}: "
                        f"{target.provider_slug}:{target.external_id} {outcome}"
                    ),
                )
                if verbose:
                    logger.info(
                        "Airing daily target processed",
                        extra={
                            "provider": target.provider_slug,
                            "external_id": target.external_id,
                            "work_id": target.work_id,
                            "outcome": outcome,
                        },
                    )
                if outcome == "failed":
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0
                if (
                    consecutive_errors
                    >= settings.SYNC_INCREMENTAL_MAX_CONSECUTIVE_ERRORS
                ):
                    raise RuntimeError("Too many consecutive airing daily errors.")

            finished = end_index + 1 >= len(targets)
            self._finish_window(
                shard=shard,
                current_id=end_index + 1,
                finished=finished,
            )
            result["completed"] = finished
            result["remaining_count"] = max(0, len(targets) - (end_index + 1))
            if finished:
                sync_job_service.mark_succeeded(
                    job_id=job_id,
                    result=result,
                    current_label="Airing daily queue completed",
                )
            else:
                sync_job_service.mark_succeeded(
                    job_id=job_id,
                    result=result,
                    current_label="Airing daily batch completed",
                )
            return result
        except Exception as exc:
            self._fail_window(shard=shard, current_id=end_index + 1)
            sync_job_service.mark_failed(
                job_id=job_id,
                error=exc,
                current_label="Airing daily batch failed",
            )
            raise

    def _refresh_target(self, target: AiringTarget) -> str:
        try:
            if target.provider_slug == "bangumi":
                subject_service.upsert_subject(int(target.external_id))
                episode_service.sync_subject_episodes(int(target.external_id))
            elif target.provider_slug == "anilist":
                anilist_import_service.import_media(int(target.external_id))
            elif target.provider_slug == "mal":
                mal_import_service.import_anime(int(target.external_id))
            else:
                return "skipped"
            return "synced"
        except BangumiAPIError as exc:
            if exc.is_not_found:
                return "skipped"
            logger.warning(
                "Airing daily provider request failed",
                extra={
                    "provider": target.provider_slug,
                    "external_id": target.external_id,
                    "work_id": target.work_id,
                },
                exc_info=True,
            )
            self._record_error(entity_id=target.external_id)
            return "failed"
        except Exception:
            logger.exception(
                "Airing daily target failed",
                extra={
                    "provider": target.provider_slug,
                    "external_id": target.external_id,
                    "work_id": target.work_id,
                },
            )
            self._record_error(entity_id=target.external_id)
            return "failed"

    @staticmethod
    def _record_error(*, entity_id: str) -> None:
        try:
            numeric_id = int(entity_id)
        except (TypeError, ValueError):
            return
        error, created = SyncError.objects.get_or_create(
            task_name=AiringDailySyncService.TASK_NAME,
            entity_id=numeric_id,
        )
        if not created:
            SyncError.objects.filter(pk=error.pk).update(
                retry_count=F("retry_count") + 1,
            )

    @staticmethod
    @transaction.atomic
    def _start_window(
        *,
        shard: str,
        total_count: int,
        batch_size: int,
    ) -> tuple[int, int] | None:
        state = (
            SyncState.objects.select_for_update()
            .filter(task_name=AiringDailySyncService.TASK_NAME, shard=shard)
            .first()
        )
        if state is None:
            state = SyncState.objects.create(
                task_name=AiringDailySyncService.TASK_NAME,
                shard=shard,
                current_id=0,
                end_id=0,
                status=SyncState.Status.IDLE,
            )
        if state.status == SyncState.Status.RUNNING:
            return None
        start = min(state.current_id, total_count - 1)
        end = min(start + batch_size - 1, total_count - 1)
        state.end_id = end
        state.status = SyncState.Status.RUNNING
        state.save(update_fields=["end_id", "status", "updated_at"])
        return start, end

    @staticmethod
    def _finish_window(*, shard: str, current_id: int, finished: bool) -> None:
        SyncState.objects.filter(
            task_name=AiringDailySyncService.TASK_NAME,
            shard=shard,
        ).update(
            current_id=current_id,
            status=(SyncState.Status.FINISHED if finished else SyncState.Status.IDLE),
            updated_at=timezone.now(),
        )

    @staticmethod
    def _fail_window(*, shard: str, current_id: int) -> None:
        SyncState.objects.filter(
            task_name=AiringDailySyncService.TASK_NAME,
            shard=shard,
        ).update(
            current_id=current_id,
            status=SyncState.Status.FAILED,
            fail_count=F("fail_count") + 1,
            updated_at=timezone.now(),
        )

    @staticmethod
    def _serialize_state(state: SyncState | None) -> dict | None:
        if state is None:
            return None
        return {
            "task_name": state.task_name,
            "shard": state.shard,
            "current_id": state.current_id,
            "end_id": state.end_id,
            "status": state.status,
            "fail_count": state.fail_count,
            "updated_at": state.updated_at,
        }


airing_daily_sync_service = AiringDailySyncService()
