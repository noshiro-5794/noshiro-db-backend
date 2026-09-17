from unittest.mock import patch

import pytest

from apps.index.models import (
    AiringBoardEntry,
    AiringEvent,
    Entity,
    Observation,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
    Work,
)
from apps.index.services.airing_board import airing_board_service
from apps.sync.models import SyncState
from apps.sync.services.airing_daily_sync_service import airing_daily_sync_service

pytestmark = pytest.mark.django_db(transaction=True)


def _calendar_board(*ids: int) -> Observation:
    provider, _ = Provider.objects.get_or_create(
        slug="bangumi",
        defaults={"name": "Bangumi", "storage_policy": "allowed"},
    )
    subject_ns, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug="subject",
        defaults={"resource_type": ProviderNamespace.ResourceType.SUBJECT},
    )
    calendar_ns, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug="calendar",
        defaults={"resource_type": ProviderNamespace.ResourceType.SCHEDULE},
    )
    observation = Observation.objects.create(
        provider_record=ProviderRecord.objects.create(
            namespace=calendar_ns,
            external_id="weekly",
            origin=ProviderRecord.Origin.API,
            status=ProviderRecord.Status.ACTIVE,
        ),
        origin=Observation.Origin.LEGACY,
        schema_name="index.schedule",
        schema_version="1",
        normalized_data={"groups": []},
        normalized_hash="calendar-hash",
    )
    for index, external_id in enumerate(ids, start=1):
        record = ProviderRecord.objects.create(
            namespace=subject_ns,
            external_id=str(external_id),
            origin=ProviderRecord.Origin.API,
            status=ProviderRecord.Status.ACTIVE,
        )
        entity = Entity.objects.create(kind=Entity.Kind.WORK)
        Work.objects.create(entity=entity, work_type=Work.WorkType.ANIME)
        ProviderRepresentation.objects.create(
            provider_record=record,
            entity=entity,
            mapping_kind=ProviderRepresentation.MappingKind.EXACT,
            method=ProviderRepresentation.Method.EXTERNAL_ID,
        )
        AiringEvent.objects.create(
            work_id=entity.id,
            weekday=index,
            precision=AiringEvent.Precision.WEEKDAY,
            raw_value="Weekday",
            observation=observation,
        )
    airing_board_service.refresh(
        observation=observation,
        season_key="2026Q3",
        item_count=len(ids),
    )
    return observation


def test_daily_refresh_processes_board_in_bounded_batches() -> None:
    _calendar_board(101, 102)
    calls: list[int] = []

    def _upsert(bangumi_id: int):
        calls.append(bangumi_id)
        return Entity.objects.first()

    with (
        patch(
            "apps.sync.services.airing_daily_sync_service.subject_service.upsert_subject",
            side_effect=_upsert,
        ),
        patch(
            "apps.sync.services.airing_daily_sync_service.episode_service.sync_subject_episodes"
        ) as episodes,
    ):
        first = airing_daily_sync_service.sync_day(batch_size=1)
        second = airing_daily_sync_service.sync_day(batch_size=1)
        third = airing_daily_sync_service.sync_day(batch_size=1)

    assert calls == [101, 102]
    assert episodes.call_count == 2
    assert first["processed_count"] == 1
    assert first["completed"] is False
    assert second["processed_count"] == 1
    assert second["completed"] is True
    assert third["processed_count"] == 0
    assert third["completed"] is True
    state = SyncState.objects.get(
        task_name=airing_daily_sync_service.TASK_NAME,
        shard=first["shard"],
    )
    assert state.status == SyncState.Status.FINISHED
    assert state.current_id == 2


def test_daily_status_reports_current_shard() -> None:
    _calendar_board(101)
    status = airing_daily_sync_service.get_status(season_key="2026Q3")
    assert status["state"] is None

    airing_daily_sync_service.sync_day(batch_size=1)
    status = airing_daily_sync_service.get_status(season_key="2026Q3")
    assert status["state"] is not None
    assert status["state"]["status"] == SyncState.Status.FINISHED


def test_daily_targets_include_board_projection_provider_records() -> None:
    provider, _ = Provider.objects.get_or_create(
        slug="mal",
        defaults={"name": "MyAnimeList", "storage_policy": "allowed"},
    )
    namespace, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug="anime",
        defaults={"resource_type": ProviderNamespace.ResourceType.SUBJECT},
    )
    record = ProviderRecord.objects.create(
        namespace=namespace,
        external_id="5114",
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
    board = airing_board_service.refresh(
        observation=None,
        season_key="2026Q3",
        item_count=1,
    )
    AiringBoardEntry.objects.create(
        board=board,
        work_id=entity.id,
        weekday=2,
        precision=AiringBoardEntry.Precision.WEEKDAY,
        source_refs=[
            {"provider": "mal", "external_id": "5114"},
        ],
    )

    targets, _ = airing_daily_sync_service.board_targets()

    assert len(targets) == 1
    assert targets[0].provider_slug == "mal"
    assert targets[0].external_id == "5114"
    assert targets[0].work_id == str(entity.id)


def test_cancel_stale_seasons_retires_old_sync_shards() -> None:
    old = SyncState.objects.create(
        task_name="airing_daily",
        shard="airing_daily:2026-09-30:2026Q3",
        current_id=1,
        end_id=5,
        status=SyncState.Status.RUNNING,
    )
    current = SyncState.objects.create(
        task_name="airing_daily",
        shard="airing_daily:2026-10-04:2026Q4",
        current_id=0,
        end_id=5,
        status=SyncState.Status.RUNNING,
    )

    retired = airing_daily_sync_service.cancel_stale_seasons(active_season_key="2026Q4")

    assert retired == 1
    old.refresh_from_db()
    current.refresh_from_db()
    assert old.status == SyncState.Status.FINISHED
    assert current.status == SyncState.Status.RUNNING
