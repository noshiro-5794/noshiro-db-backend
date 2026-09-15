"""One-command season reconciliation across AniList, MAL, and Bangumi.

Source legs run independently and are isolated from each other: a provider
outage (or any failure inside one leg) is recorded in the source summary and
does not prevent the remaining sources from being refreshed. This keeps the
future daily season task useful while one upstream API is under maintenance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.index.models import ProviderRecord
from apps.sync.providers.anilist import ANILIST_SEASON_ITEM_NAMESPACE
from apps.sync.services.anilist_season_service import anilist_season_service
from apps.sync.services.anilist_service import anilist_import_service
from apps.sync.services.mal_season_pipeline import mal_season_pipeline_service


class SeasonPipelineService:
    """Promote seasonal sources and reconcile their cross-provider identity."""

    def run(
        self,
        *,
        max_items_per_source: int | None = None,
        evaluate: bool = False,
    ) -> dict[str, Any]:
        sources = {
            "anilist": self._run_isolated(
                lambda: self._run_anilist_leg(max_items_per_source)
            ),
            "mal": self._run_isolated(lambda: self._run_mal_leg(max_items_per_source)),
        }
        created_ids = self._created_candidate_ids(sources)
        if evaluate and created_ids:
            self._dispatch_ai_evaluations(created_ids)

        anilist_detail = _detail(sources.get("anilist"))
        mal_detail = _detail(sources.get("mal"))
        anilist_ids = anilist_detail.get("candidate_ids") or []
        return {
            "sources": sources,
            "overall": self._overall_status(sources),
            # Legacy convenience aliases kept for existing callers/CLI output.
            "anilist_snapshot": anilist_detail.get("snapshot"),
            "anilist_imported": anilist_detail.get("imported"),
            "anilist_candidates": (
                {"created": len(anilist_ids), "ids": anilist_ids}
                if anilist_detail
                else None
            ),
            "mal": mal_detail or None,
            "ai_evaluations_dispatched": len(created_ids) if evaluate else 0,
        }

    def _run_anilist_leg(self, max_items: int | None) -> dict[str, Any]:
        """Refresh the AniList season snapshot, then promote its saved items."""
        snapshot = anilist_season_service.sync_current_airing()
        imported = self._promote_anilist_records(max_items=max_items)
        candidates = self._generate_anilist_candidates()
        candidate_ids = list(candidates.get("created_ids") or [])
        return {
            "snapshot": snapshot,
            "imported": len(imported),
            "candidates": candidates,
            "candidate_ids": candidate_ids,
        }

    def _run_mal_leg(self, max_items: int | None) -> dict[str, Any]:
        """Refresh the MAL season listing and promote its entities."""
        return mal_season_pipeline_service.run(
            fetch_season=True,
            evaluate=False,
            max_items=max_items,
        )

    @staticmethod
    def _run_isolated(runner: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """Run one source leg and turn any failure into a source summary."""
        try:
            detail = runner()
        except Exception as exc:
            unavailable_reason = getattr(exc, "unavailable_reason", None)
            return {
                "status": "unavailable" if unavailable_reason else "failed",
                "unavailable_reason": unavailable_reason,
                "error": f"{type(exc).__name__}: {exc}",
                "retryable": bool(getattr(exc, "retryable", False)),
                "retry_after": getattr(exc, "retry_after", None),
            }
        return {"status": "succeeded", "detail": detail}

    @classmethod
    def _created_candidate_ids(cls, sources: dict[str, dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        detail_keys = {
            "anilist": "candidates",
            "mal": "mal_candidates",
        }
        for source, key in detail_keys.items():
            detail = _detail(sources.get(source))
            if not detail:
                continue
            for candidate_id in (detail.get(key) or {}).get("created_ids") or []:
                if candidate_id not in seen:
                    seen.add(candidate_id)
                    ordered.append(candidate_id)
        return ordered

    @staticmethod
    def _overall_status(sources: dict[str, dict[str, Any]]) -> str:
        statuses = [summary["status"] for summary in sources.values()]
        if all(status == "succeeded" for status in statuses):
            return "succeeded"
        if any(status == "succeeded" for status in statuses):
            return "partial"
        return "failed"

    def _promote_anilist_records(self, *, max_items: int | None) -> list[str]:
        external_ids = (
            ProviderRecord.objects.filter(
                namespace__provider__slug="anilist",
                namespace__slug=ANILIST_SEASON_ITEM_NAMESPACE.slug,
                status=ProviderRecord.Status.ACTIVE,
                latest_revision__isnull=False,
            )
            .order_by("external_id")
            .values_list("external_id", flat=True)
            .distinct()
        )
        if max_items:
            external_ids = external_ids[: max(1, int(max_items))]
        imported: list[str] = []
        for external_id in external_ids:
            try:
                entity = anilist_import_service.import_saved_media(int(external_id))
            except (TypeError, ValueError):
                continue
            if entity is not None:
                imported.append(str(entity.id))
        return imported

    def _generate_anilist_candidates(self) -> dict[str, Any]:
        from apps.index.services import provider_candidate_service

        return provider_candidate_service.generate_candidates(
            source_provider="anilist",
            source_namespace="anime",
            target_provider="bangumi",
            target_namespace="subject",
            min_similarity=0.6,
            top_k=5,
            create=True,
        )

    def _dispatch_ai_evaluations(self, candidate_ids: list[str]) -> None:
        from config.celery import app as celery_app

        for candidate_id in candidate_ids:
            celery_app.send_task(
                "apps.ai.tasks.evaluate_match_candidate_task",
                args=[candidate_id],
                queue="ai",
            )


def _detail(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not summary or summary.get("status") != "succeeded":
        return {}
    detail = summary.get("detail")
    return detail if isinstance(detail, dict) else {}


season_pipeline_service = SeasonPipelineService()
