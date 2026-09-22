from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.index.models import (
    AiringBoard,
    AiringBoardEntry,
    AnimeProfile,
    Entity,
    Observation,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
    Work,
)
from apps.index.services import (
    airing_board_projection_service,
    knowledge_ingestion_service,
)
from apps.index.services.airing_board_projection import (
    CandidateBar,
    _choose_bar,
    _corroborates,
    _format_allowed,
    _season_switch_allowed,
)
from apps.sync.providers.contracts import (
    CatalogSourceSpec,
    FetchedSourceRecord,
    SourceNamespaceSpec,
)
from apps.sync.services.source_record_service import source_record_service

pytestmark = pytest.mark.django_db(transaction=True)


def _anime_entity(
    *, provider_slug: str, namespace_slug: str, external_id: str
) -> Entity:
    provider, _ = Provider.objects.get_or_create(
        slug=provider_slug,
        defaults={"name": provider_slug.title()},
    )
    namespace, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug=namespace_slug,
        defaults={"resource_type": ProviderNamespace.ResourceType.SUBJECT},
    )
    record = ProviderRecord.objects.create(
        namespace=namespace,
        external_id=external_id,
        origin="api",
        status="active",
    )
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    Work.objects.create(entity=entity, work_type=Work.WorkType.ANIME)
    ProviderRepresentation.objects.create(
        provider_record=record,
        entity=entity,
        mapping_kind=ProviderRepresentation.MappingKind.EXACT,
        method=ProviderRepresentation.Method.PROVIDER,
    )
    return entity


def _current_season_key() -> str:
    now = timezone.localtime()
    return f"{now.year}Q{(now.month - 1) // 3 + 1}"


def _record_mal_season_observation(
    *, mal_id: int, item_overrides: dict | None = None
) -> ProviderRecord:
    source = CatalogSourceSpec(
        slug="mal",
        name="MyAnimeList",
        base_url="https://myanimelist.net",
    )
    season_namespace = SourceNamespaceSpec(
        source=source,
        slug="season",
        resource_type=ProviderNamespace.ResourceType.SCHEDULE,
    )
    now = timezone.now().astimezone(ZoneInfo("Asia/Tokyo"))
    tomorrow = (now + timedelta(days=1)).strftime("%A").lower()
    season_key = _current_season_key()
    item = {
        "mal_id": mal_id,
        "media_type": "tv",
        "status": "currently_airing",
        "start_date": "2026-07-01",
        "broadcast_day": tomorrow,
        "broadcast_time": "22:00",
        "timezone": "Asia/Tokyo",
        "duration_minutes": 24,
        **(item_overrides or {}),
    }
    recorded = source_record_service.record(
        namespace_spec=season_namespace,
        fetched=FetchedSourceRecord(
            external_id=f"season-now:{season_key}",
            payload={"season_key": season_key, "pages": []},
            canonical_url=(f"https://api.myanimelist.net/v2/anime/season/{season_key}"),
            schema_version="mal-api-v2",
            mapper_version="mal-season-v2",
        ),
    )
    knowledge_ingestion_service.record_observation(
        provider_record=recorded.record,
        mapper="mal.season",
        mapper_version="mal-season-v2",
        normalized_data={
            "season_key": season_key,
            "items": [item],
        },
        schema_name="index.schedule",
        schema_version="2",
    )
    return recorded.record


def test_rebuild_projects_mal_season_onto_one_board_entry() -> None:
    entity = _anime_entity(
        provider_slug="mal",
        namespace_slug="anime",
        external_id="5114",
    )
    _record_mal_season_observation(mal_id=5114)

    summary = airing_board_projection_service.rebuild()

    assert summary["entries"] == 1
    board = AiringBoard.objects.get(status=AiringBoard.Status.ACTIVE)
    entry = AiringBoardEntry.objects.get(board=board)
    assert entry.work_id == entity.id
    assert entry.precision == AiringBoardEntry.Precision.MINUTE
    assert entry.status == AiringBoardEntry.Status.SCHEDULED
    assert entry.source_refs[0]["provider"] == "mal"


def test_rebuild_keeps_a_released_film_as_a_weekdayless_day_bar() -> None:
    entity = _anime_entity(
        provider_slug="mal",
        namespace_slug="anime",
        external_id="63011",
    )
    _record_mal_season_observation(
        mal_id=63011,
        item_overrides={
            "media_type": "movie",
            "status": "finished_airing",
            "start_date": "2026-07-24",
            "broadcast_day": None,
            "broadcast_time": None,
        },
    )

    airing_board_projection_service.rebuild()

    entry = AiringBoardEntry.objects.get(work_id=entity.id)
    assert entry.weekday is None
    assert entry.precision == AiringBoardEntry.Precision.DAY
    assert entry.source_refs[0]["role"] == "date-primary"


def test_rebuild_ignores_promos_and_music_videos_in_the_season_snapshot() -> None:
    _anime_entity(provider_slug="mal", namespace_slug="anime", external_id="64001")
    _record_mal_season_observation(
        mal_id=64001,
        item_overrides={
            "media_type": "pv",
            "status": "finished_airing",
            "start_date": "2026-08-01",
            "broadcast_day": None,
            "broadcast_time": None,
        },
    )

    summary = airing_board_projection_service.rebuild()

    assert summary["entries"] == 0


def test_board_endpoint_returns_projected_bar() -> None:
    entity = _anime_entity(
        provider_slug="mal",
        namespace_slug="anime",
        external_id="5000",
    )
    _record_mal_season_observation(mal_id=5000)
    airing_board_projection_service.rebuild()

    response = APIClient().get("/api/v1/index/calendar/board/events/?include_work=true")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["work_id"] == str(entity.id)
    assert payload[0]["precision"] == "minute"
    assert payload[0]["work"]["id"] == str(entity.id)


def test_board_endpoint_labels_format_for_weekdayless_extras() -> None:
    entity = _anime_entity(
        provider_slug="mal", namespace_slug="anime", external_id="63012"
    )
    AnimeProfile.objects.create(
        work=Work.objects.get(entity=entity),
        format="MOVIE",
    )
    _record_mal_season_observation(
        mal_id=63012,
        item_overrides={
            "media_type": "movie",
            "status": "finished_airing",
            "start_date": "2026-08-12",
            "broadcast_day": None,
            "broadcast_time": None,
        },
    )
    airing_board_projection_service.rebuild()

    payload = (
        APIClient().get("/api/v1/index/calendar/board/events/?include_work=true").json()
    )

    assert len(payload) == 1
    assert payload[0]["weekday"] is None
    assert payload[0]["precision"] == "day"
    assert payload[0]["format"]


def test_rebuild_includes_not_yet_aired_premiere_inside_window() -> None:
    entity = _anime_entity(
        provider_slug="mal",
        namespace_slug="anime",
        external_id="62907",
    )
    local_now = timezone.now().astimezone(ZoneInfo("Asia/Tokyo"))
    premiere_day = (local_now + timedelta(days=2)).date().isoformat()
    _record_mal_season_observation(mal_id=62907)

    observation = Observation.objects.get(
        provider_record__external_id=f"season-now:{_current_season_key()}",
        schema_name="index.schedule",
    )
    normalized = observation.normalized_data
    normalized["items"][0].update(
        {
            "status": "not_yet_aired",
            "start_date": premiere_day,
            "broadcast_time": "20:00",
        }
    )
    observation.normalized_data = normalized
    observation.save(update_fields=["normalized_data"])

    airing_board_projection_service.rebuild()

    entry = AiringBoardEntry.objects.get(board__status=AiringBoard.Status.ACTIVE)
    assert entry.work_id == entity.id
    assert entry.starts_at is not None
    assert entry.precision == AiringBoardEntry.Precision.MINUTE


def test_candidate_fusion_prefers_anilist_minute_and_keeps_mal_evidence() -> None:
    slot = datetime(2026, 9, 16, 13, 0, tzinfo=UTC)
    mal = CandidateBar(
        entity_id="work",
        weekday=3,
        starts_at=slot,
        precision=AiringBoardEntry.Precision.MINUTE,
        provider="mal",
    )
    anilist = CandidateBar(
        entity_id="work",
        weekday=3,
        starts_at=slot + timedelta(minutes=5),
        precision=AiringBoardEntry.Precision.MINUTE,
        provider="anilist",
    )

    chosen = _choose_bar([mal, anilist])

    assert chosen is anilist
    assert _corroborates(chosen, mal) is True


def test_format_filter_excludes_music_but_allows_tv_and_unknown() -> None:
    assert _format_allowed("TV") is True
    assert _format_allowed("tv") is True
    assert _format_allowed("") is True
    assert _format_allowed("MUSIC") is False


def test_season_switch_waits_for_the_grace_period() -> None:
    with override_settings(SEASON_SWITCH_GRACE_DAYS=3):
        assert _season_switch_allowed("2026Q4", today=date(2026, 10, 2)) is False
        assert _season_switch_allowed("2026Q4", today=date(2026, 10, 4)) is True
