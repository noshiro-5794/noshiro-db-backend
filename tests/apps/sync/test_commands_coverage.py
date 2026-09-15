from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db(transaction=True)


def _run(*args) -> str:
    out = StringIO()
    call_command(*args, stdout=out)
    return out.getvalue()


def test_sync_mal_schedule_command_reports_summary() -> None:
    with patch(
        "apps.sync.services.mal_schedule_service.mal_schedule_service.sync",
        return_value={"season": {"season_key": "2026Q3", "items_seen": 0}},
    ) as sync:
        output = _run("sync_mal_schedule")

    sync.assert_called_once()
    assert '"season_key": "2026Q3"' in output


def test_sync_mal_season_command_runs_pipeline() -> None:
    with patch(
        "apps.sync.management.commands.sync_mal_season.mal_season_pipeline_service.run",
        return_value={"imported_entities": 1, "board_projection": {}},
    ) as run:
        output = _run("sync_mal_season", "--evaluate")

    run.assert_called_once_with(
        fetch_season=True,
        evaluate=True,
        max_items=None,
    )
    assert '"imported_entities": 1' in output


def test_sync_mal_command_imports_one_anime() -> None:
    with patch(
        "apps.sync.management.commands.sync_mal.mal_import_service.import_anime",
        return_value=type("E", (), {"id": "entity-1"})(),
    ) as run:
        output = _run("sync_mal", "5114")

    run.assert_called_once_with(5114)
    assert "entity-1" in output


def test_reconcile_mal_identities_command_runs_service() -> None:
    with patch(
        "apps.sync.management.commands.reconcile_mal_identities.mal_identity_service.reconcile_official_links",
        return_value={"bound": 0},
    ) as run:
        output = _run("reconcile_mal_identities", "--dry-run")

    run.assert_called_once_with(create=False, apply=False)
    assert '"bound": 0' in output


def test_rebuild_airing_board_command_runs_projection() -> None:
    with patch(
        "apps.sync.management.commands.rebuild_airing_board.airing_board_projection_service.rebuild",
        return_value={"entries": 0},
    ) as run:
        output = _run("rebuild_airing_board")

    run.assert_called_once_with()
    assert '"entries": 0' in output


def test_generate_match_candidates_supports_mal_source() -> None:
    with patch(
        "apps.sync.management.commands.generate_match_candidates.provider_candidate_service.generate_mal_bangumi_candidates",
        return_value={"source_entities": 0, "candidates_created": 0, "pairs": []},
    ) as run:
        output = _run("generate_match_candidates", "--source", "mal", "--dry-run")

    run.assert_called_once_with(min_similarity=0.6, top_k=5, create=False)
    assert "mal_entities=0" in output


def test_sync_anilist_season_command_runs_service() -> None:
    with patch(
        "apps.sync.management.commands.sync_anilist_season.anilist_season_service.sync_current_airing",
        return_value={"season_key": "fall:2026", "pages": 0},
    ) as run:
        output = _run("sync_anilist_season")

    run.assert_called_once_with(page_size=50, max_pages=40)
    assert '"season_key": "fall:2026"' in output


def test_schedule_coverage_command_reports_sources() -> None:
    with patch(
        "apps.sync.management.commands.schedule_coverage.schedule_coverage_service.report",
        return_value={"sources": {"bangumi": {}, "anilist": {}, "mal": {}}},
    ) as run:
        output = _run("schedule_coverage")

    run.assert_called_once_with()
    assert '"anilist": {}' in output


def test_complete_airing_times_command_runs_service() -> None:
    with patch(
        "apps.sync.management.commands.complete_airing_times.schedule_completion_service.run",
        return_value={"pending": 0, "accepted": 0},
    ) as run:
        output = _run("complete_airing_times", "--limit", "5")

    run.assert_called_once_with(limit=5, apply=True)
    assert '"accepted": 0' in output


def test_sync_season_command_runs_pipeline() -> None:
    with patch(
        "apps.sync.management.commands.sync_season.season_pipeline_service.run",
        return_value={"anilist_imported": 0, "ai_evaluations_dispatched": 0},
    ) as run:
        output = _run("sync_season", "--evaluate", "--max-items-per-source", "3")

    run.assert_called_once_with(max_items_per_source=3, evaluate=True)
    assert '"anilist_imported": 0' in output
