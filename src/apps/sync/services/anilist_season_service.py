"""Durable persistence for AniList current-season anime schedules."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.anilist import (
    ANILIST_SEASON_ITEM_NAMESPACE,
    ANILIST_SEASON_NAMESPACE,
    anilist_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.provider_snapshot_retention_service import (
    provider_snapshot_retention_service,
)
from apps.sync.services.source_record_service import source_record_service


class AniListSeasonSyncService:
    TASK_NAME = "anilist_season"
    DEFAULT_PAGE_SIZE = 50
    DEFAULT_MAX_PAGES = 40

    def sync_current_season(
        self,
        *,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        season, season_year = current_anilist_season()
        return self.sync_season(
            season=season,
            season_year=season_year,
            page_size=page_size,
            max_pages=max_pages,
        )

    def sync_current_airing(
        self,
        *,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        """Sync every currently releasing anime, including continuing works.

        The MAL seasonal endpoint used as the board spine includes shows that
        started in earlier seasons, so an AniList season-only query silently
        excludes long-running entries. This mode queries by release status
        instead and keeps the season label only for reporting.
        """
        season, season_year = current_anilist_season()
        page_size = max(1, int(page_size or self.DEFAULT_PAGE_SIZE))
        max_pages = max(1, int(max_pages or self.DEFAULT_MAX_PAGES))
        pages: list[dict[str, Any]] = []
        item_payloads: dict[str, dict[str, Any]] = {}
        next_cursor: str | None = None
        page_count = 0
        while page_count < max_pages:
            page_count += 1
            page_data = anilist_client.fetch_airing_page(
                cursor=next_cursor,
                page_size=page_size,
            )
            pages.append(page_data)
            for item in page_data.get("media") or []:
                if isinstance(item, dict) and isinstance(item.get("id"), int):
                    item_payloads[str(item["id"])] = item
            page_info = page_data.get("pageInfo") or {}
            if (
                not isinstance(page_info, dict)
                or page_info.get("hasNextPage") is not True
            ):
                break
            next_cursor = str(page_count + 1)

        season_key = f"{season.lower()}:{season_year}"
        recorded = source_record_service.record(
            namespace_spec=ANILIST_SEASON_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id="airing:current",
                payload={
                    "season": season,
                    "season_year": season_year,
                    "mode": "airing",
                    "pages": pages,
                },
                canonical_url="https://anilist.co/browse/anime",
                schema_version="anilist-graphql",
                mapper_version="anilist-airing-list-v1",
                fetched_at=timezone.now(),
            ),
        )
        knowledge_ingestion_service.record_observation(
            provider_record=recorded.record,
            mapper="anilist.airing-list",
            mapper_version="anilist-airing-list-v1",
            normalized_data={
                "season": season,
                "season_year": season_year,
                "mode": "airing",
                "pages": pages,
            },
            schema_name="index.schedule",
            schema_version="1",
        )
        provider_snapshot_retention_service.retain_current(recorded.record)
        item_ids = self._record_season_items(item_payloads)
        return {
            "season_key": season_key,
            "mode": "airing",
            "pages": len(pages),
            "season_record_id": str(recorded.record.id),
            "changed": recorded.changed,
            "items_seen": len(item_payloads),
            "items_recorded": len(item_ids),
        }

    def sync_season(
        self,
        *,
        season: str,
        season_year: int,
        page_size: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        page_size = max(1, int(page_size or self.DEFAULT_PAGE_SIZE))
        max_pages = max(1, int(max_pages or self.DEFAULT_MAX_PAGES))
        pages: list[dict[str, Any]] = []
        item_payloads: dict[str, dict[str, Any]] = {}
        next_cursor: str | None = None
        page_count = 0
        while page_count < max_pages:
            page_count += 1
            page_data = anilist_client.fetch_season_page(
                season=season,
                season_year=season_year,
                cursor=next_cursor,
                page_size=page_size,
            )
            pages.append(page_data)
            for item in page_data.get("media") or []:
                if isinstance(item, dict) and isinstance(item.get("id"), int):
                    item_payloads[str(item["id"])] = item
            page_info = page_data.get("pageInfo") or {}
            if (
                not isinstance(page_info, dict)
                or page_info.get("hasNextPage") is not True
            ):
                break
            next_cursor = str(page_count + 1)

        season_key = f"{season.lower()}:{season_year}"
        recorded = source_record_service.record(
            namespace_spec=ANILIST_SEASON_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=f"season:{season_key}",
                payload={
                    "season": season,
                    "season_year": season_year,
                    "pages": pages,
                },
                canonical_url="https://anilist.co/browse/anime",
                schema_version="anilist-graphql",
                mapper_version="anilist-season-v1",
                fetched_at=timezone.now(),
            ),
        )
        knowledge_ingestion_service.record_observation(
            provider_record=recorded.record,
            mapper="anilist.season-now",
            mapper_version="anilist-season-v1",
            normalized_data={
                "season": season,
                "season_year": season_year,
                "pages": pages,
            },
            schema_name="index.schedule",
            schema_version="1",
        )
        provider_snapshot_retention_service.retain_current(recorded.record)
        item_ids = self._record_season_items(item_payloads)
        return {
            "season_key": season_key,
            "pages": len(pages),
            "season_record_id": str(recorded.record.id),
            "changed": recorded.changed,
            "items_seen": len(item_payloads),
            "items_recorded": len(item_ids),
        }

    @staticmethod
    def _record_season_items(items: dict[str, dict[str, Any]]) -> list[str]:
        if not items:
            return []
        fetched = [
            FetchedSourceRecord(
                external_id=external_id,
                payload=payload,
                canonical_url=f"https://anilist.co/anime/{external_id}",
                schema_version="anilist-graphql",
                mapper_version="anilist-season-item-v1",
                fetched_at=timezone.now(),
            )
            for external_id, payload in items.items()
        ]
        recorded = source_record_service.record_many(
            namespace_spec=ANILIST_SEASON_ITEM_NAMESPACE,
            fetched_records=fetched,
        )
        return [
            str(item.record.id)
            for external_id in items
            if (item := recorded.get(external_id)) is not None
        ]


anilist_season_service = AniListSeasonSyncService()


def current_anilist_season() -> tuple[str, int]:
    """Return AniList season name/year for the local broadcast quarter."""
    today = timezone.localdate()
    month = today.month
    if month in {1, 2, 3}:
        return "WINTER", today.year
    if month in {4, 5, 6}:
        return "SPRING", today.year
    if month in {7, 8, 9}:
        return "SUMMER", today.year
    return "FALL", today.year
