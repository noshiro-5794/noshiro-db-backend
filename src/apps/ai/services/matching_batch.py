"""Bounded dispatch of pending match candidates to the cheap AI tier."""

from __future__ import annotations

from typing import Any

from apps.index.models import MatchCandidate
from config.celery import app as celery_app


class AIMatchingBatchService:
    def pending_candidates(self, *, limit: int) -> list[MatchCandidate]:
        return list(
            MatchCandidate.objects.filter(
                status=MatchCandidate.Status.PENDING,
                ai_proposals__isnull=True,
            ).order_by("created_at", "id")[: max(1, int(limit))]
        )

    def dispatch(self, *, limit: int) -> dict[str, Any]:
        candidates = self.pending_candidates(limit=limit)
        candidate_ids = [str(candidate.pk) for candidate in candidates]
        for candidate_id in candidate_ids:
            celery_app.send_task(
                "apps.ai.tasks.evaluate_match_candidate_task",
                args=[candidate_id],
                queue="ai",
            )
        return {
            "dispatched": len(candidate_ids),
            "candidate_ids": candidate_ids,
        }


ai_matching_batch_service = AIMatchingBatchService()
