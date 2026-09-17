"""Quarter rollover orchestration for the multi-source airing board.

The board is a single active window. Around a quarter boundary this service
prefetches the next source snapshots but keeps the previous board visible until
the configured grace period passes, then runs the full season pipeline and
retires the old daily-sync shard.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.index.models import AiringBoard
from apps.index.services.airing_board_projection import (
    _season_switch_allowed,
    _season_switch_date,
)
from apps.sync.services.airing_daily_sync_service import airing_daily_sync_service
from apps.sync.services.anilist_season_service import anilist_season_service
from apps.sync.services.calendar_service import calendar_sync_service
from apps.sync.services.mal_schedule_service import mal_schedule_service
from apps.sync.services.season_pipeline_service import season_pipeline_service


class SeasonRolloverService:
    def current_season_key(self) -> str:
        now = timezone.localtime()
        return f"{now.year}Q{(now.month - 1) // 3 + 1}"

    def status(self) -> dict[str, Any]:
        board = (
            AiringBoard.objects.filter(status=AiringBoard.Status.ACTIVE)
            .only("season_key", "metadata", "item_count")
            .first()
        )
        current = self.current_season_key()
        return {
            "active_season": board.season_key if board else "",
            "current_season": current,
            "rollover_pending": bool(board and board.season_key != current),
            "switch_date": _season_switch_date(current).isoformat(),
            "grace_days": int(settings.SEASON_SWITCH_GRACE_DAYS),
            "item_count": board.item_count if board else 0,
        }

    def run(self) -> dict[str, Any]:
        board = (
            AiringBoard.objects.filter(status=AiringBoard.Status.ACTIVE)
            .select_related("observation")
            .first()
        )
        current = self.current_season_key()
        if board is None:
            pipeline = season_pipeline_service.run(
                max_items_per_source=None,
                evaluate=False,
            )
            return {"action": "initialized", "pipeline": pipeline}
        if board.season_key == current:
            return {"action": "none", "season_key": current}

        # Prefetch the next sources without switching the active board.
        prefetch = {
            "mal": self._safe(mal_schedule_service.sync),
            "anilist": self._safe(anilist_season_service.sync_current_airing),
            "bangumi": self._safe(
                lambda: calendar_sync_service.sync_calendar(sync_subject_details=False)
            ),
        }
        if not _season_switch_allowed(current, today=timezone.localdate()):
            return {
                "action": "prefetched",
                "pending_season": current,
                "active_season": board.season_key,
                "prefetch": prefetch,
            }

        pipeline = season_pipeline_service.run(
            max_items_per_source=None,
            evaluate=False,
        )
        board.refresh_from_db()
        retired = 0
        if board.season_key == current:
            retired = airing_daily_sync_service.cancel_stale_seasons(
                active_season_key=current
            )
        return {
            "action": "switched" if board.season_key == current else "failed",
            "season_key": current,
            "prefetch": prefetch,
            "pipeline": pipeline,
            "retired_sync_shards": retired,
        }

    @staticmethod
    def _safe(callable_) -> dict[str, Any]:
        try:
            return {"status": "succeeded", "result": callable_()}
        except Exception as exc:
            return {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}"[:2000],
            }


season_rollover_service = SeasonRolloverService()
