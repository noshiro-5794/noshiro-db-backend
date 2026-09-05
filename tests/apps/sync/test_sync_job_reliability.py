from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.sync.models import SyncJob, SyncState
from apps.sync.services.incremental_sync_service import IncrementalSyncService
from apps.sync.services.sync_job_service import sync_job_service
from apps.sync.tasks.maintenance import (
    scan_stale_sync_jobs,
    scan_stale_sync_states,
    worker_heartbeat,
)


def _create_job(**kwargs) -> SyncJob:
    return SyncJob.objects.create(
        job_type=SyncJob.JobType.INCREMENTAL,
        **kwargs,
    )


@pytest.mark.django_db
def test_claim_heartbeat_release_and_stale_detection() -> None:
    job = _create_job()
    now = timezone.now()

    assert sync_job_service.claim(
        job_id=job.id,
        lease_owner="worker-a",
        lease_seconds=60,
    )

    job.refresh_from_db()
    assert job.status == SyncJob.Status.RUNNING
    assert job.attempt == 1
    assert job.lease_owner == "worker-a"
    assert job.lease_expires_at is not None
    assert job.lease_expires_at > now
    assert job.started_at is not None

    assert not sync_job_service.claim(
        job_id=job.id,
        lease_owner="worker-b",
        lease_seconds=60,
    )

    previous_lease = job.lease_expires_at
    assert sync_job_service.heartbeat(
        job_id=job.id,
        lease_owner="worker-a",
        lease_seconds=120,
    )
    job.refresh_from_db()
    assert job.lease_expires_at > previous_lease

    sync_job_service.release(job_id=job.id, lease_owner="worker-a")
    job.refresh_from_db()
    assert job.lease_expires_at <= timezone.now()

    stale_job = _create_job(
        status=SyncJob.Status.RUNNING,
        lease_owner="worker-lost",
        lease_expires_at=timezone.now() - timedelta(seconds=10),
    )
    assert sync_job_service.stale_running_jobs().filter(pk=stale_job.pk).exists()


@pytest.mark.django_db
def test_stale_job_scan_marks_expired_lease_as_failed() -> None:
    stale_job = _create_job(
        status=SyncJob.Status.RUNNING,
        lease_owner="worker-lost",
        lease_expires_at=timezone.now() - timedelta(seconds=10),
    )

    result = scan_stale_sync_jobs()

    stale_job.refresh_from_db()
    assert result == {"stale_jobs": 1}
    assert stale_job.status == SyncJob.Status.FAILED
    assert "Lease expired" in stale_job.error


def _sync_state(**kwargs) -> SyncState:
    return SyncState.objects.create(
        task_name="incremental_subject",
        shard=IncrementalSyncService.SHARD,
        end_id=1000,
        **kwargs,
    )


@pytest.mark.django_db
def test_record_progress_refreshes_updated_at() -> None:
    state = _sync_state(status=SyncState.Status.RUNNING)
    SyncState.objects.filter(pk=state.pk).update(
        updated_at=timezone.now() - timedelta(hours=2)
    )

    IncrementalSyncService._record_progress(
        task_name="incremental_subject",
        current_id=42,
    )

    state.refresh_from_db()
    assert state.current_id == 42
    assert state.updated_at > timezone.now() - timedelta(minutes=1)


@pytest.mark.django_db
@override_settings(SYNC_STALE_STATE_SECONDS=60)
def test_stale_state_scan_unlocks_only_old_running_windows() -> None:
    stale = _sync_state(status=SyncState.Status.RUNNING)
    active = _sync_state(
        task_name="incremental_episode",
        status=SyncState.Status.RUNNING,
    )
    SyncState.objects.filter(pk=stale.pk).update(
        updated_at=timezone.now() - timedelta(hours=2)
    )

    result = scan_stale_sync_states()

    assert result == {"stale_states": 1}
    stale.refresh_from_db()
    active.refresh_from_db()
    assert stale.status == SyncState.Status.FAILED
    assert stale.fail_count == 1
    assert active.status == SyncState.Status.RUNNING


@pytest.mark.django_db
def test_worker_heartbeat_writes_recent_cache_marker() -> None:
    result = worker_heartbeat()

    assert result["heartbeat_at"]
    assert cache.get("noshiro:beat:heartbeat") == result["heartbeat_at"]


@pytest.mark.django_db
def test_stale_job_scan_ignores_active_leases() -> None:
    active_job = _create_job(
        status=SyncJob.Status.RUNNING,
        lease_owner="worker-a",
        lease_expires_at=timezone.now() + timedelta(seconds=60),
    )

    result = scan_stale_sync_jobs()

    active_job.refresh_from_db()
    assert result == {"stale_jobs": 0}
    assert active_job.status == SyncJob.Status.RUNNING
