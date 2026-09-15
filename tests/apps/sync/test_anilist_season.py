from datetime import date
from unittest.mock import patch

import pytest

from apps.index.models import AiringEvent, Entity, Observation, ProviderRecord, Work
from apps.sync.providers.anilist import (
    ANILIST_SEASON_ITEM_NAMESPACE,
    ANILIST_SEASON_NAMESPACE,
    anilist_client,
)
from apps.sync.services.anilist_season_service import (
    anilist_season_service,
    current_anilist_season,
)
from apps.sync.services.schedule_coverage_service import schedule_coverage_service

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.mark.parametrize(
    ("month", "season"),
    [
        (1, "WINTER"),
        (3, "WINTER"),
        (4, "SPRING"),
        (6, "SPRING"),
        (7, "SUMMER"),
        (9, "SUMMER"),
        (10, "FALL"),
        (12, "FALL"),
    ],
)
def test_current_anilist_season_mapping(month: int, season: str) -> None:
    with patch(
        "apps.sync.services.anilist_season_service.timezone.localdate",
        return_value=date(2026, month, 15),
    ):
        assert current_anilist_season() == (season, 2026)


def _season_page(*, has_next: bool = False) -> dict:
    return {
        "pageInfo": {"hasNextPage": has_next, "total": 1},
        "media": [
            {
                "id": 189046,
                "idMal": 60073,
                "type": "ANIME",
                "format": "TV",
                "status": "RELEASING",
                "season": "FALL",
                "seasonYear": 2026,
                "episodes": 12,
                "duration": 24,
                "isAdult": False,
                "siteUrl": "https://anilist.co/anime/189046",
                "startDate": {"year": 2026, "month": 9, "day": 1},
                "endDate": None,
                "nextAiringEpisode": {"airingAt": 1800000000, "episode": 1},
                "title": {
                    "romaji": "Test Anime",
                    "english": "Test Anime",
                    "native": "テストアニメ",
                    "userPreferred": "Test Anime",
                },
                "coverImage": {"extraLarge": "https://example.test/cover.jpg"},
                "airingSchedule": {
                    "nodes": [{"id": 1, "episode": 1, "airingAt": 1800000000}]
                },
            }
        ],
    }


def test_season_sync_records_snapshot_and_item_records() -> None:
    with patch.object(
        anilist_client,
        "fetch_season_page",
        return_value=_season_page(),
    ) as fetch:
        summary = anilist_season_service.sync_season(
            season="FALL",
            season_year=2026,
        )

    assert summary["season_key"] == "fall:2026"
    assert summary["pages"] == 1
    assert summary["items_recorded"] == 1
    fetch.assert_called_once()
    season_record = ProviderRecord.objects.get(
        namespace__provider__slug="anilist",
        namespace__slug=ANILIST_SEASON_NAMESPACE.slug,
        external_id="season:fall:2026",
    )
    assert Observation.objects.filter(
        provider_record=season_record,
        schema_name="index.schedule",
    ).exists()
    assert ProviderRecord.objects.filter(
        namespace__provider__slug="anilist",
        namespace__slug=ANILIST_SEASON_ITEM_NAMESPACE.slug,
        external_id="189046",
    ).exists()


def test_season_sync_is_idempotent() -> None:
    page = _season_page()
    with patch.object(anilist_client, "fetch_season_page", return_value=page):
        anilist_season_service.sync_season(season="FALL", season_year=2026)
        anilist_season_service.sync_season(season="FALL", season_year=2026)

    assert (
        ProviderRecord.objects.filter(
            namespace__provider__slug="anilist",
            namespace__slug=ANILIST_SEASON_ITEM_NAMESPACE.slug,
            external_id="189046",
        ).count()
        == 1
    )


def test_season_sync_feeds_schedule_coverage_report() -> None:
    with patch.object(anilist_client, "fetch_season_page", return_value=_season_page()):
        anilist_season_service.sync_season(season="FALL", season_year=2026)

    report = schedule_coverage_service.report()

    assert report["sources"]["anilist"]["item_count"] == 1
    assert report["sources"]["mal"]["item_count"] == 0
    assert report["sources"]["bangumi"]["board_item_count"] == 0


def test_season_item_can_be_promoted_to_canonical_entity() -> None:
    from apps.sync.services.anilist_service import anilist_import_service

    with patch.object(anilist_client, "fetch_season_page", return_value=_season_page()):
        anilist_season_service.sync_season(season="FALL", season_year=2026)

    entity = anilist_import_service.import_saved_media(189046)

    assert entity.kind == Entity.Kind.WORK
    work = Work.objects.get(entity=entity)
    assert work.work_type == Work.WorkType.ANIME
    assert AiringEvent.objects.filter(work=work).count() >= 1


def test_season_query_variables_are_bounded() -> None:
    with patch.object(
        anilist_client,
        "_post",
        return_value={"Page": _season_page()},
    ) as post:
        result = anilist_client.fetch_season_page(
            season="FALL",
            season_year=2026,
            cursor="3",
            page_size=50,
        )

    assert result["pageInfo"]["hasNextPage"] is False
    variables = post.call_args.args[1]
    assert variables == {
        "page": 3,
        "perPage": 50,
        "season": "FALL",
        "seasonYear": 2026,
    }
