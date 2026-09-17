"""Durable seasonal persistence for MAL data fetched through the official API.

MyAnimeList v2 has no weekly schedule endpoint, so the board source is the
official **seasonal listing**. One idempotent ``mal/season`` snapshot keeps
the point-in-time broadcast facts (used by the board projection), while each
season anime is mirrored under ``mal/schedule-item`` so the MAL season
pipeline can promote entities without re-fetching the full season.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.timezone import localdate

from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.providers.mal import (
    MAL_SCHEDULE_ITEM_NAMESPACE,
    MAL_SEASON_NAMESPACE,
    mal_api_client,
    season_name_for_quarter,
)
from apps.sync.services.provider_snapshot_retention_service import (
    provider_snapshot_retention_service,
)
from apps.sync.services.source_record_service import source_record_service
from apps.sync.services.sync_job_service import sync_job_service


class MALScheduleService:
    """Fetch and record the official MAL current-season listing."""

    TASK_NAME = "mal_schedule"
    DEFAULT_LIMIT = 500
    DEFAULT_MAX_PAGES = 10
    TIMEZONE = "Asia/Tokyo"

    def sync(
        self,
        *,
        job_id: str | None = None,
        limit: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        limit = max(1, int(limit or self.DEFAULT_LIMIT))
        max_pages = max(1, int(max_pages or self.DEFAULT_MAX_PAGES))
        sync_job_service.mark_running(
            job_id=job_id,
            total_count=1,
            current_label="Fetching MAL current-season listing",
        )
        try:
            season = self.sync_current_season(limit=limit, max_pages=max_pages)
        except Exception as exc:
            sync_job_service.mark_failed(
                job_id=job_id,
                error=exc,
                current_label="MAL seasonal sync failed",
            )
            raise
        result = {
            "source": "mal",
            "season": season,
            "fetched_at": timezone.now().isoformat(),
        }
        sync_job_service.mark_succeeded(
            job_id=job_id,
            result=result,
            current_label="MAL seasonal sync completed",
        )
        return result

    def sync_current_season(
        self,
        *,
        limit: int = 500,
        max_pages: int = 10,
    ) -> dict[str, Any]:
        today = localdate()
        quarter = (today.month - 1) // 3 + 1
        year = today.year
        mal_season = season_name_for_quarter(quarter)
        season_key = f"{year}Q{quarter}"

        pages: list[dict[str, Any]] = []
        item_payloads: dict[str, dict[str, Any]] = {}
        offset = 0
        page_count = 0
        while page_count < max_pages:
            page_count += 1
            payload = mal_api_client.fetch_season(
                year=year,
                season=mal_season,
                offset=offset,
                limit=limit,
            )
            pages.append(payload)
            nodes = self._nodes(payload)
            for node in nodes:
                mal_id = node.get("id")
                if isinstance(mal_id, int):
                    item_payloads[str(mal_id)] = node
            if not nodes or not self._has_next_page(payload):
                break
            offset += len(nodes)

        recorded = self._record_season_snapshot(
            season_key=season_key,
            mal_season=mal_season,
            year=year,
            pages=pages,
            items=list(item_payloads.values()),
        )
        item_ids = self._record_anime_items(item_payloads)
        return {
            "season_key": season_key,
            "mal_season": mal_season,
            "pages": len(pages),
            "schedule_record_id": str(recorded.record.id),
            "changed": recorded.changed,
            "items_seen": len(item_payloads),
            "items_recorded": len(item_ids),
        }

    @staticmethod
    def _nodes(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        nodes: list[dict[str, Any]] = []
        for wrapper in data:
            if not isinstance(wrapper, dict):
                continue
            node = (
                wrapper.get("node")
                if isinstance(wrapper.get("node"), dict)
                else wrapper
            )
            if isinstance(node, dict):
                nodes.append(node)
        return nodes

    @staticmethod
    def _has_next_page(payload: dict[str, Any]) -> bool:
        paging = payload.get("paging") if isinstance(payload, dict) else {}
        return isinstance(paging, dict) and bool(paging.get("next"))

    def _record_season_snapshot(
        self,
        *,
        season_key: str,
        mal_season: str,
        year: int,
        pages: list[dict[str, Any]],
        items: list[dict[str, Any]],
    ) -> Any:
        external_id = f"season-now:{season_key}"
        recorded = source_record_service.record(
            namespace_spec=MAL_SEASON_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=external_id,
                payload={
                    "season_key": season_key,
                    "year": year,
                    "season": mal_season,
                    "pages": pages,
                },
                canonical_url=(
                    f"https://api.myanimelist.net/v2/anime/season/{year}/{mal_season}"
                ),
                schema_version="mal-api-v2",
                mapper_version="mal-season-v2",
                fetched_at=timezone.now(),
            ),
        )
        knowledge_ingestion_service.record_observation(
            provider_record=recorded.record,
            mapper="mal.season",
            mapper_version="mal-season-v2",
            normalized_data={
                "season_key": season_key,
                "year": year,
                "season": mal_season,
                "items": [self._normalized_item(item) for item in items],
            },
            schema_name="index.schedule",
            schema_version="2",
        )
        provider_snapshot_retention_service.retain_current(recorded.record)
        return recorded

    @classmethod
    def _normalized_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        broadcast = (
            item.get("broadcast") if isinstance(item.get("broadcast"), dict) else {}
        )
        episode_duration = item.get("average_episode_duration")
        duration_minutes = None
        if isinstance(episode_duration, int) and episode_duration > 0:
            duration_minutes = max(1, round(episode_duration / 60))
        return {
            "mal_id": item.get("id"),
            "media_type": item.get("media_type"),
            "status": item.get("status"),
            "start_date": item.get("start_date"),
            "broadcast_day": broadcast.get("day_of_the_week"),
            "broadcast_time": broadcast.get("start_time"),
            "timezone": cls.TIMEZONE if broadcast else "",
            "duration_minutes": duration_minutes,
        }

    @staticmethod
    def _record_anime_items(
        items: dict[str, dict[str, Any]],
    ) -> list[str]:
        if not items:
            return []
        fetched_records = [
            FetchedSourceRecord(
                external_id=external_id,
                payload=payload,
                canonical_url=(f"https://myanimelist.net/anime/{external_id}"),
                schema_version="mal-api-v2",
                mapper_version="mal-season-item-v2",
                fetched_at=timezone.now(),
            )
            for external_id, payload in items.items()
        ]
        recorded = source_record_service.record_many(
            namespace_spec=MAL_SCHEDULE_ITEM_NAMESPACE,
            fetched_records=fetched_records,
        )
        return [
            str(item.record.id)
            for external_id in items
            if (item := recorded.get(external_id)) is not None
        ]


mal_schedule_service = MALScheduleService()
