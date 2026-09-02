from unittest.mock import Mock, patch

from django.test import override_settings

from apps.sync.api.serializers.import_jobs import ImportJobQuerySerializer
from apps.sync.models import SyncError, SyncState
from apps.sync.providers.bangumi import BangumiAPIError
from apps.sync.services.calendar_image_service import CalendarImageService
from apps.sync.services.data_mapping import clean_string
from apps.sync.services.incremental_sync_service import (
    IncrementalSyncService,
    IncrementalTaskConfig,
)
from apps.sync.tasks.base import BaseSyncTask
from apps.sync.tasks.full_sync import FullEpisodeSyncTask


def test_bangumi_not_found_error_is_structured() -> None:
    assert BangumiAPIError("missing", status_code=404).is_not_found is True
    assert BangumiAPIError("failed", status_code=503).is_not_found is False


def test_external_strings_are_stripped_and_bounded() -> None:
    assert clean_string("  value  ", max_length=4) == "valu"
    assert clean_string(None, max_length=4) == ""


@override_settings(BANGUMI_IMAGE_ALLOWED_HOSTS=["lain.bgm.tv"])
def test_calendar_images_only_allow_configured_http_hosts() -> None:
    assert CalendarImageService._is_allowed_url("https://lain.bgm.tv/pic/cover.jpg")
    assert CalendarImageService._is_allowed_url("https://cdn.lain.bgm.tv/pic/cover.jpg")
    assert not CalendarImageService._is_allowed_url("file:///etc/passwd")
    assert not CalendarImageService._is_allowed_url(
        "https://lain.bgm.tv.example.com/cover.jpg"
    )


@override_settings(
    BANGUMI_IMAGE_ALLOWED_HOSTS=["lain.bgm.tv"],
    BANGUMI_TIMEOUT=30,
    BANGUMI_USER_AGENT="test-agent",
)
def test_calendar_image_client_follows_http_redirects() -> None:
    with patch("apps.sync.services.calendar_image_service.httpx.Client") as factory:
        client = CalendarImageService().client

    factory.assert_called_once()
    kwargs = factory.call_args.kwargs
    assert kwargs["follow_redirects"] is True
    assert kwargs["headers"]["User-Agent"] == "test-agent"
    assert client is factory.return_value


def test_incremental_not_found_is_skipped_without_recording_an_error() -> None:
    config = IncrementalTaskConfig(
        task_name="example",
        full_task_name="full_example",
        handler_name="_sync_subject",
        cursor_source="subject",
    )

    with (
        patch.object(
            IncrementalSyncService,
            "_sync_subject",
            side_effect=BangumiAPIError("missing", status_code=404),
        ),
        patch.object(IncrementalSyncService, "_record_error") as record_error,
    ):
        outcome = IncrementalSyncService._sync_one(config=config, bangumi_id=123)

    assert outcome == "skipped"
    record_error.assert_not_called()


def test_full_sync_treats_provider_not_found_as_a_completed_entity() -> None:
    handler = Mock(side_effect=BangumiAPIError("missing", status_code=404))

    assert BaseSyncTask()._safe_handle(handler, 123) is True
    handler.assert_called_once_with(123)


def test_full_episode_sync_filters_by_bangumi_source() -> None:
    with patch(
        "apps.sync.tasks.full_sync._has_bangumi_subject",
        return_value=False,
    ) as has_subject:
        FullEpisodeSyncTask().sync_one(123)

    has_subject.assert_called_once_with(123)


def test_sync_job_list_query_rejects_unknown_filters() -> None:
    serializer = ImportJobQuerySerializer(data={"status": "stuck"})

    assert not serializer.is_valid()
    assert set(serializer.errors) == {"status"}


def test_sync_models_do_not_redeclare_unique_constraint_indexes() -> None:
    assert SyncError._meta.indexes == []
    assert SyncState._meta.indexes == []
