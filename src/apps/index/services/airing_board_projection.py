"""Multi-source weekly board projection (the Gantt-ready board layer).

``AiringEvent`` rows stay immutable per-source facts. This service rebuilds the
curated ``AiringBoardEntry`` window for the active board from those facts plus
MAL broadcast rules, after canonical identity resolution, so the calendar can
draw one bar per canonical work instead of per source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.index.models import (
    AiringBoard,
    AiringBoardEntry,
    AiringEvent,
    AnimeProfile,
    Entity,
    Observation,
    ProviderRepresentation,
    Work,
)
from apps.index.selectors.current import active_airing_board_events
from apps.index.services.airing_board import airing_board_service
from apps.index.services.resolution import entity_resolution_service

_WEEKDAY_MAP = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}

# Source roles are field-level rather than provider-level:
# * AniList owns the precise per-episode instant (airingAt);
# * MAL owns the weekly broadcast slot and is the identity spine;
# * Bangumi is the coverage fallback for works absent from both.
_MINUTE_SOURCE_PRIORITY = {"anilist": 0, "mal": 1, "bangumi": 2}
_WEEKDAY_SOURCE_PRIORITY = {"mal": 0, "anilist": 1, "bangumi": 2}
_DEFAULT_ALLOWED_FORMATS = ("TV", "TV_SHORT", "ONA")
_FORMAT_ALIASES = {
    "TV": "TV",
    "TV_SHORT": "TV_SHORT",
    "ONA": "ONA",
    "WEB": "ONA",
}

# Films, OVAs and specials are part of the season but have no weekly slot, so
# the board keeps them in a separate bucket below the weekday columns instead
# of dropping them. Promos, commercials and music videos stay out entirely.
_EXTRA_MEDIA_FORMATS = {
    "movie": "MOVIE",
    "ova": "OVA",
    "special": "SPECIAL",
    "tv_special": "SPECIAL",
}
_EXTRA_STATUSES = {"currently_airing", "not_yet_aired", "finished_airing"}


@dataclass(frozen=True, slots=True)
class CandidateBar:
    """One source-supplied bar waiting for canonical deduplication."""

    entity_id: Any
    weekday: int
    starts_at: datetime | None = None
    timezone: str = ""
    duration_minutes: int | None = None
    episode_number: int | None = None
    precision: str = AiringBoardEntry.Precision.WEEKDAY
    status: str = AiringBoardEntry.Status.TENTATIVE
    provider: str = ""
    format: str = ""
    observation_id: Any = None
    external_id: str = ""


class AiringBoardProjectionService:
    def rebuild(self) -> dict[str, Any]:
        board = self._ensure_board()
        candidates = self._candidates_for_window(season_key=board.season_key)
        entries = self._project_candidates(candidates, board=board)
        with transaction.atomic():
            AiringBoardEntry.objects.filter(board=board).delete()
            if entries:
                AiringBoardEntry.objects.bulk_create(entries)
            airing_board_service.refresh(
                observation=board.observation,
                season_key=board.season_key,
                item_count=len(entries),
                metadata={
                    "projection": "field-fusion-v2",
                    "candidate_count": len(candidates),
                    "generated_at": timezone.now().isoformat(),
                },
            )
        return {
            "board_id": str(board.id),
            "season_key": board.season_key,
            "entries": len(entries),
            "candidates": len(candidates),
        }

    @staticmethod
    def _ensure_board() -> AiringBoard:
        board = (
            AiringBoard.objects.filter(status=AiringBoard.Status.ACTIVE)
            .select_related("observation")
            .first()
        )
        if board is None:
            board = airing_board_service.refresh(
                observation=None,
                season_key="",
                item_count=0,
            )
        now = timezone.localtime()
        season_key = f"{now.year}Q{(now.month - 1) // 3 + 1}"
        if board.season_key != season_key:
            if _season_switch_allowed(season_key, today=now.date()):
                return airing_board_service.refresh(
                    observation=board.observation,
                    season_key=season_key,
                    item_count=0,
                )
            metadata = dict(board.metadata or {})
            metadata["rollover_pending"] = season_key
            metadata["rollover_effective_on"] = _season_switch_date(
                season_key
            ).isoformat()
            board.metadata = metadata
            board.save(update_fields=["metadata", "updated_at"])
        return board

    def _candidates_for_window(self, *, season_key: str) -> list[CandidateBar]:
        now = timezone.now()
        end = now + timedelta(days=7)
        formats = self._format_index()
        candidates: list[CandidateBar] = []
        candidates.extend(self._bangumi_weekday_candidates(formats=formats))
        candidates.extend(
            self._anilist_minute_candidates(now=now, end=end, formats=formats)
        )
        candidates.extend(
            self._mal_season_candidates(
                now=now,
                end=end,
                season_key=season_key,
            )
        )
        # Weekday bars obey the TV calendar allow-list; the weekday-less extras
        # carry their own format gate when they are built.
        return [
            bar
            for bar in candidates
            if bar.weekday is None or _format_allowed(bar.format)
        ]

    @staticmethod
    def _format_index() -> dict[Any, str]:
        rows = AnimeProfile.objects.filter(work__entity_id__isnull=False).values_list(
            "work__entity_id", "format"
        )
        return {entity_id: str(format_value or "") for entity_id, format_value in rows}

    @staticmethod
    def _bangumi_weekday_candidates(
        *,
        formats: dict[Any, str],
    ) -> list[CandidateBar]:
        bars: list[CandidateBar] = []
        for event in active_airing_board_events().filter(
            precision=AiringEvent.Precision.WEEKDAY
        ):
            root = _canonical_entity(event.work.entity)
            if root is None:
                continue
            bars.append(
                CandidateBar(
                    entity_id=root.id,
                    weekday=event.weekday,
                    precision=AiringBoardEntry.Precision.WEEKDAY,
                    provider="bangumi",
                    format=formats.get(root.id, ""),
                    observation_id=event.observation_id,
                )
            )
        return bars

    @staticmethod
    def _anilist_minute_candidates(
        *,
        now: datetime,
        end: datetime,
        formats: dict[Any, str],
    ) -> list[CandidateBar]:
        bars: list[CandidateBar] = []
        events = (
            AiringEvent.objects.filter(
                starts_at__gte=now,
                starts_at__lt=end,
                precision=AiringEvent.Precision.MINUTE,
                work__work_type=Work.WorkType.ANIME,
                observation__provider_record__namespace__provider__slug="anilist",
                observation__provider_record__namespace__slug="calendar",
            )
            .select_related("work__entity", "observation")
            .order_by("starts_at")
        )
        for event in events:
            root = _canonical_entity(event.work.entity)
            if root is None:
                continue
            bars.append(
                CandidateBar(
                    entity_id=root.id,
                    weekday=event.starts_at.weekday() + 1 if event.starts_at else None,
                    starts_at=event.starts_at,
                    timezone=event.timezone or "UTC",
                    precision=AiringBoardEntry.Precision.MINUTE,
                    status=AiringBoardEntry.Status.SCHEDULED,
                    provider="anilist",
                    format=formats.get(root.id, ""),
                    observation_id=event.observation_id,
                )
            )
        return bars

    def _mal_season_candidates(
        self,
        *,
        now: datetime,
        end: datetime,
        season_key: str,
    ) -> list[CandidateBar]:
        bars: list[CandidateBar] = []
        mal_works = self._mal_work_index()
        records = Observation.objects.filter(
            schema_name="index.schedule",
            current_projections__provider_record__namespace__provider__slug="mal",
            current_projections__provider_record__namespace__slug="season",
        )
        for observation in records:
            normalized = observation.normalized_data or {}
            if normalized.get("season_key") != season_key:
                continue
            for item in normalized.get("items") or []:
                if not isinstance(item, dict):
                    continue
                bar = self._mal_item_bar(
                    item=item,
                    mal_works=mal_works,
                    observation_id=observation.id,
                    now=now,
                    end=end,
                )
                if bar is not None:
                    bars.append(bar)
        return bars

    @staticmethod
    def _mal_item_bar(
        *,
        item: dict[str, Any],
        mal_works: dict[int, Any],
        observation_id: Any,
        now: datetime,
        end: datetime,
    ) -> CandidateBar | None:
        mal_id = item.get("mal_id")
        if not isinstance(mal_id, int) or mal_id not in mal_works:
            return None
        status = str(item.get("status") or "").lower().replace(" ", "_")
        weekday = _WEEKDAY_MAP.get(str(item.get("broadcast_day") or "").strip().lower())
        if weekday is None:
            return _mal_extra_bar(
                item=item,
                entity_id=mal_works[mal_id],
                observation_id=observation_id,
                status=status,
            )
        is_airing = status == "currently_airing"
        is_upcoming = status == "not_yet_aired"
        if not (is_airing or is_upcoming):
            return None
        raw_time = item.get("broadcast_time")
        timezone_name = str(item.get("timezone") or "Asia/Tokyo")
        starts_at = None
        if is_upcoming:
            starts_at = _premiere_occurrence(
                start_date=item.get("start_date"),
                raw_time=raw_time if isinstance(raw_time, str) else "",
                timezone_name=timezone_name,
                now=now,
            )
        elif isinstance(raw_time, str) and ":" in raw_time:
            try:
                hour, minute = raw_time.split(":", 1)
                slot = _next_occurrence(
                    weekday=weekday,
                    hour=int(hour),
                    minute=int(minute[:2]),
                    timezone_name=timezone_name,
                    now=now,
                )
                starts_at = slot
            except ValueError:
                starts_at = None
        if starts_at is not None and not (now <= starts_at < end):
            return None
        entity_id = mal_works[mal_id]
        effective_weekday = (
            starts_at.weekday() + 1 if starts_at is not None else weekday
        )
        return CandidateBar(
            entity_id=entity_id,
            weekday=effective_weekday,
            starts_at=starts_at,
            timezone=timezone_name,
            duration_minutes=_as_positive_int(item.get("duration_minutes")),
            precision=(
                AiringBoardEntry.Precision.MINUTE
                if starts_at is not None
                else AiringBoardEntry.Precision.WEEKDAY
            ),
            status=AiringBoardEntry.Status.SCHEDULED,
            provider="mal",
            format=str(item.get("media_type") or ""),
            observation_id=observation_id,
            external_id=str(mal_id),
        )

    @staticmethod
    def _mal_work_index() -> dict[int, Any]:
        rows = (
            ProviderRepresentation.objects.filter(
                is_active=True,
                provider_record__namespace__provider__slug="mal",
                provider_record__namespace__slug="anime",
                entity__lifecycle=Entity.Lifecycle.ACTIVE,
            )
            .select_related("entity")
            .values_list("provider_record__external_id", "entity_id")
        )
        index: dict[int, Any] = {}
        for external_id, entity_id in rows:
            try:
                index[int(external_id)] = entity_id
            except (TypeError, ValueError):
                continue
        return index

    @staticmethod
    def _project_candidates(
        candidates: list[CandidateBar],
        *,
        board: AiringBoard,
    ) -> list[AiringBoardEntry]:
        grouped: dict[tuple[Any, int | None], list[CandidateBar]] = {}
        for bar in candidates:
            grouped.setdefault((bar.entity_id, bar.weekday), []).append(bar)
        entries: list[AiringBoardEntry] = []
        for (entity_id, weekday), bars in grouped.items():
            work = Work.objects.filter(entity_id=entity_id).first()
            if work is None:
                continue
            chosen = _choose_bar(bars)
            agrees = [bar for bar in bars if _corroborates(chosen, bar)]
            source_refs = [
                {
                    "provider": bar.provider,
                    "namespace": (
                        "subject"
                        if bar.provider == "bangumi"
                        else "anime"
                        if bar.provider == "mal"
                        else "calendar"
                    ),
                    "external_id": bar.external_id,
                    "observation_id": str(bar.observation_id)
                    if bar.observation_id
                    else "",
                    "precision": bar.precision,
                    "starts_at": bar.starts_at.isoformat() if bar.starts_at else "",
                    "role": _source_role(chosen=chosen, bar=bar),
                }
                for bar in [chosen, *agrees]
            ]
            entries.append(
                AiringBoardEntry(
                    board=board,
                    work=work,
                    weekday=weekday,
                    starts_at=chosen.starts_at,
                    timezone=chosen.timezone,
                    duration_minutes=chosen.duration_minutes,
                    precision=chosen.precision,
                    status=chosen.status,
                    decision=(
                        AiringBoardEntry.Decision.CONSENSUS
                        if agrees
                        else AiringBoardEntry.Decision.SOURCE_PRIORITY
                    ),
                    confidence=(Decimal("1.0000") if agrees else Decimal("0.9500")),
                    source_refs=source_refs,
                )
            )
        return entries


airing_board_projection_service = AiringBoardProjectionService()


def _mal_extra_bar(
    *,
    item: dict[str, Any],
    entity_id: Any,
    observation_id: Any,
    status: str,
) -> CandidateBar | None:
    """Build a date-only bar for a film, OVA or special in the season snapshot."""
    format_name = _EXTRA_MEDIA_FORMATS.get(
        str(item.get("media_type") or "").strip().lower()
    )
    if format_name is None or status not in _EXTRA_STATUSES:
        return None
    start_date = _as_date(item.get("start_date"))
    if start_date is None:
        return None
    starts_at = datetime.combine(
        start_date,
        time(hour=0, minute=0),
        tzinfo=ZoneInfo("Asia/Tokyo"),
    ).astimezone(UTC)
    return CandidateBar(
        entity_id=entity_id,
        weekday=None,
        starts_at=starts_at,
        timezone="Asia/Tokyo",
        precision=AiringBoardEntry.Precision.DAY,
        status=AiringBoardEntry.Status.SCHEDULED,
        provider="mal",
        format=format_name,
        observation_id=observation_id,
        external_id=str(item.get("mal_id") or ""),
    )


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _canonical_entity(entity: Entity) -> Entity | None:
    if entity.kind != Entity.Kind.WORK:
        return None
    root = entity_resolution_service.resolve(entity)
    if (
        root.lifecycle != Entity.Lifecycle.ACTIVE
        or not Work.objects.filter(entity=root).exists()
    ):
        return None
    return root


def _allowed_formats() -> set[str]:
    configured = (
        getattr(settings, "CALENDAR_ALLOWED_FORMATS", None) or _DEFAULT_ALLOWED_FORMATS
    )
    return {
        _FORMAT_ALIASES.get(str(value).strip().upper(), str(value).strip().upper())
        for value in configured
    }


def _format_allowed(value: Any) -> bool:
    raw = str(value or "").strip().upper()
    if not raw:
        return True  # Unknown formats stay visible rather than silently dropping.
    return _FORMAT_ALIASES.get(raw, raw) in _allowed_formats()


def _choose_bar(bars: list[CandidateBar]) -> CandidateBar:
    """Pick the fused bar: precise instant first, then provider role."""
    minute_bars = [bar for bar in bars if bar.starts_at is not None]
    if minute_bars:
        return min(
            minute_bars,
            key=lambda bar: (
                _MINUTE_SOURCE_PRIORITY.get(bar.provider, 99),
                bar.starts_at,
            ),
        )
    return min(
        bars,
        key=lambda bar: _WEEKDAY_SOURCE_PRIORITY.get(bar.provider, 99),
    )


def _corroborates(chosen: CandidateBar, other: CandidateBar) -> bool:
    if other is chosen or other.provider == chosen.provider:
        return False
    if chosen.starts_at is None or other.starts_at is None:
        return True
    return abs((other.starts_at - chosen.starts_at).total_seconds()) <= 1800


def _source_role(*, chosen: CandidateBar, bar: CandidateBar) -> str:
    if bar is chosen:
        if bar.precision == AiringBoardEntry.Precision.MINUTE:
            return "precise" if bar.provider == "anilist" else "primary"
        if bar.precision == AiringBoardEntry.Precision.DAY:
            return "date-primary"
        return "weekday-primary"
    if bar.precision == AiringBoardEntry.Precision.MINUTE:
        return "corroboration"
    if bar.precision == AiringBoardEntry.Precision.DAY:
        return "date-corroboration"
    return "weekday-corroboration"


def _season_start_date(season_key: str) -> date | None:
    value = (season_key or "").strip().upper()
    if len(value) != 6 or value[4] != "Q" or value[-1] not in "1234":
        return None
    try:
        year = int(value[:4])
    except ValueError:
        return None
    quarter = int(value[-1])
    return date(year, 1 + (quarter - 1) * 3, 1)


def _season_switch_date(season_key: str) -> date:
    start = _season_start_date(season_key)
    if start is None:
        return timezone.localdate()
    return start + timedelta(days=int(getattr(settings, "SEASON_SWITCH_GRACE_DAYS", 3)))


def _season_switch_allowed(season_key: str, *, today: date) -> bool:
    start = _season_start_date(season_key)
    if start is None:
        return True
    return today >= _season_switch_date(season_key)


def _next_occurrence(
    *,
    weekday: int,
    hour: int,
    minute: int,
    timezone_name: str,
    now: datetime,
) -> datetime | None:
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("Asia/Tokyo")
    local_now = now.astimezone(zone)
    days_ahead = (weekday - local_now.isoweekday()) % 7
    local_slot = datetime.combine(
        local_now.date() + timedelta(days=days_ahead),
        time(hour=hour, minute=minute),
        tzinfo=zone,
    )
    if local_slot <= local_now:
        local_slot += timedelta(days=7)
    return local_slot.astimezone(UTC)


def _premiere_occurrence(
    *,
    start_date: Any,
    raw_time: str,
    timezone_name: str,
    now: datetime,
) -> datetime | None:
    """Return the exact premiere instant for a not-yet-aired MAL entry."""
    if not isinstance(start_date, str) or ":" not in raw_time:
        return None
    try:
        premiere_day = date.fromisoformat(start_date)
        hour, minute = raw_time.split(":", 1)
        premiere_time = time(hour=int(hour), minute=int(minute[:2]))
    except (TypeError, ValueError):
        return None
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = ZoneInfo("Asia/Tokyo")
    premiere = datetime.combine(premiere_day, premiere_time, tzinfo=zone)
    if premiere <= now:
        return None
    return premiere.astimezone(UTC)


def _as_positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
