"""Airing-board window registry.

The active board is intentionally a thin, single-row projection over the
calendar observation that owns the weekday ``AiringEvent`` rows. Membership is
never duplicated here; read it through the board's observation. Refreshes keep
the same active board while the season key is unchanged and atomically archive
the old window when the effective broadcast season rolls over.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.index.models import AiringBoard, Observation


class AiringBoardService:
    def active(self) -> AiringBoard | None:
        return (
            AiringBoard.objects.filter(status=AiringBoard.Status.ACTIVE)
            .select_related("observation")
            .first()
        )

    @transaction.atomic
    def refresh(
        self,
        *,
        observation: Observation | None,
        season_key: str = "",
        item_count: int = 0,
        metadata: dict[str, Any] | None = None,
        preserve_projection: bool = False,
    ) -> AiringBoard:
        now = timezone.now()
        season = (season_key or "").strip()
        active = (
            AiringBoard.objects.select_for_update()
            .filter(status=AiringBoard.Status.ACTIVE)
            .first()
        )
        if active is not None:
            if (active.season_key or "").strip() == season:
                active.observation = observation
                active.effective_until = None
                update_fields = ["observation", "effective_until", "updated_at"]
                if not preserve_projection:
                    active.item_count = max(0, int(item_count))
                    active.metadata = metadata or {}
                    update_fields[1:1] = ["item_count", "metadata"]
                active.save(
                    update_fields=update_fields,
                )
                return active
            active.status = AiringBoard.Status.ARCHIVED
            active.effective_until = now
            active.save(update_fields=["status", "effective_until", "updated_at"])

        board = AiringBoard.objects.create(
            observation=observation,
            season_key=season,
            status=AiringBoard.Status.ACTIVE,
            item_count=max(0, int(item_count)),
            metadata=metadata or {},
            effective_from=now,
        )
        return board

    def snapshot(self) -> dict[str, Any] | None:
        board = self.active()
        if board is None:
            return None
        return {
            "board_id": str(board.id),
            "season_key": board.season_key,
            "item_count": board.item_count,
            "observed_at": (
                board.observation.observed_at.isoformat()
                if board.observation_id is not None
                and board.observation.observed_at is not None
                else None
            ),
            "refreshed_at": board.updated_at.isoformat(),
        }


airing_board_service = AiringBoardService()
