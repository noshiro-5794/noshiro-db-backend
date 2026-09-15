from unittest.mock import patch

import pytest

from apps.sync.providers.exceptions import AniListAPIError
from apps.sync.services.season_pipeline_service import season_pipeline_service

pytestmark = pytest.mark.django_db(transaction=True)


def test_run_chains_anilist_promotion_candidates_and_mal_pipeline() -> None:
    with (
        patch.object(
            season_pipeline_service,
            "_generate_anilist_candidates",
            return_value={"created_ids": ["c1"]},
        ),
        patch.object(
            season_pipeline_service,
            "_dispatch_ai_evaluations",
        ) as dispatch,
        patch(
            "apps.sync.services.season_pipeline_service.anilist_season_service.sync_current_airing",
            return_value={"season_key": "fall:2026"},
        ),
        patch(
            "apps.sync.services.season_pipeline_service.anilist_import_service.import_saved_media",
            return_value=type("Entity", (), {"id": "anilist-1"})(),
        ),
        patch(
            "apps.sync.services.season_pipeline_service.ProviderRecord.objects.filter",
        ) as records,
        patch(
            "apps.sync.services.season_pipeline_service.mal_season_pipeline_service.run",
            return_value={"identity": {"bound": 0}},
        ) as mal_run,
    ):
        records.return_value.order_by.return_value.values_list.return_value.distinct.return_value = [
            "189046"
        ]
        result = season_pipeline_service.run(
            max_items_per_source=2,
            evaluate=True,
        )

    assert result["anilist_imported"] == 1
    assert result["ai_evaluations_dispatched"] == 1
    mal_run.assert_called_once_with(
        fetch_season=True,
        evaluate=False,
        max_items=2,
    )
    dispatch.assert_called_once_with(["c1"])


def test_anilist_maintenance_does_not_block_mal_leg() -> None:
    maintenance_error = AniListAPIError(
        "AniList returned HTTP 403: The AniList API has been temporarily "
        "disabled due to severe stability issues.",
        status_code=403,
        retry_after=900,
        unavailable_reason="provider_maintenance",
    )
    with (
        patch.object(
            season_pipeline_service,
            "_promote_anilist_records",
        ) as promote,
        patch.object(
            season_pipeline_service,
            "_generate_anilist_candidates",
        ) as generate_candidates,
        patch(
            "apps.sync.services.season_pipeline_service.anilist_season_service.sync_current_airing",
            side_effect=maintenance_error,
        ) as sync_season,
        patch(
            "apps.sync.services.season_pipeline_service.mal_season_pipeline_service.run",
            return_value={
                "mal_candidates": {"created_ids": ["m1"]},
                "identity": {"bound": 0},
            },
        ) as mal_run,
        patch.object(
            season_pipeline_service,
            "_dispatch_ai_evaluations",
        ) as dispatch,
    ):
        result = season_pipeline_service.run(evaluate=True)

    sources = result["sources"]
    assert sources["anilist"]["status"] == "unavailable"
    assert sources["anilist"]["unavailable_reason"] == "provider_maintenance"
    assert sources["anilist"]["retryable"] is True
    assert sources["mal"]["status"] == "succeeded"
    assert result["overall"] == "partial"
    assert result["anilist_imported"] is None
    sync_season.assert_called_once_with()
    promote.assert_not_called()
    generate_candidates.assert_not_called()
    mal_run.assert_called_once_with(
        fetch_season=True,
        evaluate=False,
        max_items=None,
    )
    dispatch.assert_called_once_with(["m1"])
