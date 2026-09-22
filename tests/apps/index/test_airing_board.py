import pytest

from apps.index.models import AiringBoard
from apps.index.services.airing_board import airing_board_service

from .projection_fixtures import observation

pytestmark = pytest.mark.django_db(transaction=True)


def test_refresh_within_season_updates_single_active_board() -> None:
    first = observation({"version": "board-1"})
    second = observation({"version": "board-2"})

    board = airing_board_service.refresh(
        observation=first,
        season_key="2026Q3",
        item_count=12,
        metadata={"added_ids": [1]},
    )
    same_season = airing_board_service.refresh(
        observation=second,
        season_key="2026Q3",
        item_count=10,
        metadata={"added_ids": [2]},
    )

    assert same_season.id == board.id
    assert AiringBoard.objects.filter(status=AiringBoard.Status.ACTIVE).count() == 1
    assert AiringBoard.objects.count() == 1
    assert same_season.item_count == 10
    assert same_season.metadata == {"added_ids": [2]}


def test_season_rollover_archives_previous_window_and_creates_new_active() -> None:
    old_observation = observation({"version": "board-old"})
    new_observation = observation({"version": "board-new"})

    old_board = airing_board_service.refresh(
        observation=old_observation,
        season_key="2026Q3",
        item_count=20,
    )
    new_board = airing_board_service.refresh(
        observation=new_observation,
        season_key="2026Q4",
        item_count=18,
    )

    old_board.refresh_from_db()
    assert old_board.status == AiringBoard.Status.ARCHIVED
    assert old_board.effective_until is not None
    assert new_board.status == AiringBoard.Status.ACTIVE
    assert new_board.season_key == "2026Q4"
    assert AiringBoard.objects.filter(status=AiringBoard.Status.ACTIVE).count() == 1
    assert AiringBoard.objects.count() == 2
    snapshot = airing_board_service.snapshot()
    assert snapshot is not None
    assert snapshot["board_id"] == str(new_board.id)
    assert snapshot["season_key"] == "2026Q4"


def test_refresh_can_preserve_projection_metadata() -> None:
    first = observation({"version": "projection"})
    second = observation({"version": "calendar"})
    board = airing_board_service.refresh(
        observation=first,
        season_key="2026Q3",
        item_count=150,
        metadata={"projection": "field-fusion-v2"},
    )

    refreshed = airing_board_service.refresh(
        observation=second,
        season_key="2026Q3",
        item_count=111,
        metadata={"weekday_counts": {"1": 13}},
        preserve_projection=True,
    )

    assert refreshed.id == board.id
    assert refreshed.observation_id == second.id
    assert refreshed.item_count == 150
    assert refreshed.metadata == {"projection": "field-fusion-v2"}
