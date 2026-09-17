"""Backfill provider records that were created without a raw payload."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.index.models import ProviderRecord
from apps.sync.providers.exceptions import AniListAPIError
from apps.sync.services.anilist_service import anilist_import_service


class ProviderStubBackfillService:
    """Only implement handlers that can safely fetch a full record."""

    handlers: dict[tuple[str, str], Callable[[str], Any]] = {
        ("anilist", "anime"): lambda external_id: anilist_import_service.import_media(
            int(external_id)
        ),
    }

    def report(self) -> dict[str, Any]:
        rows = (
            ProviderRecord.objects.filter(latest_revision__isnull=True)
            .values("namespace__provider__slug", "namespace__slug")
            .order_by()
        )
        summary: dict[str, int] = {}
        for row in rows:
            key = f"{row['namespace__provider__slug']}:{row['namespace__slug']}"
            summary[key] = summary.get(key, 0) + 1
        return {
            "stub_records": sum(summary.values()),
            "by_namespace": summary,
            "supported_targets": [
                f"{provider}:{namespace}"
                for provider, namespace in sorted(self.handlers)
            ],
        }

    def backfill(
        self,
        *,
        apply: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        report = self.report()
        candidates = list(
            ProviderRecord.objects.filter(latest_revision__isnull=True)
            .filter(
                namespace__provider__slug="anilist",
                namespace__slug="anime",
            )
            .order_by("external_id")
        )
        if limit:
            candidates = candidates[: max(1, int(limit))]
        result: dict[str, Any] = {
            "candidates": len(candidates),
            "backfilled": 0,
            "missing": 0,
            "failed": [],
            "report": report,
        }
        if not apply:
            return result
        handler = self.handlers[("anilist", "anime")]
        for record in candidates:
            try:
                handler(record.external_id)
                result["backfilled"] += 1
            except Exception as exc:
                if (
                    isinstance(exc, AniListAPIError)
                    and getattr(exc, "status_code", None) == 404
                ):
                    ProviderRecord.objects.filter(pk=record.pk).update(
                        status=ProviderRecord.Status.MISSING,
                        raw_state=ProviderRecord.RawState.STUB,
                    )
                    result["missing"] += 1
                    continue
                result["failed"].append(
                    {
                        "external_id": record.external_id,
                        "error": f"{type(exc).__name__}: {exc}"[:1000],
                    }
                )
        return result


provider_stub_backfill_service = ProviderStubBackfillService()
