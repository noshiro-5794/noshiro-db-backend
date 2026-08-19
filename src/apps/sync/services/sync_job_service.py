from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.sync.exceptions import SyncJobNotFound
from apps.sync.models import SyncJob


class SyncJobService:
    DEFAULT_LEASE_SECONDS = 3600

    @staticmethod
    def create_job(*, job_type: str, parameters: dict | None = None) -> SyncJob:
        return SyncJob.objects.create(
            job_type=job_type,
            parameters=parameters or {},
            status=SyncJob.Status.QUEUED,
        )

    @staticmethod
    def bind_celery_task(*, job_id: UUID | str, celery_task_id: str) -> None:
        SyncJob.objects.filter(id=job_id).update(celery_task_id=celery_task_id)

    @staticmethod
    def mark_running(
        *,
        job_id: UUID | str | None,
        total_count: int | None = None,
        current_label: str = "",
        lease_owner: str | None = None,
    ) -> None:
        if not job_id:
            return
        updates: dict[str, Any] = {
            "status": SyncJob.Status.RUNNING,
            "started_at": Coalesce("started_at", Value(timezone.now())),
            "current_label": current_label,
        }
        if total_count is not None:
            updates["total_count"] = max(0, int(total_count))
        queryset = SyncJob.objects.filter(
            id=job_id,
            status__in=(SyncJob.Status.QUEUED, SyncJob.Status.RUNNING),
        )
        if lease_owner:
            queryset = queryset.filter(lease_owner=lease_owner)
        queryset.update(**updates)

    @staticmethod
    def set_total(
        *, job_id: UUID | str | None, total_count: int, current_label: str = ""
    ) -> None:
        if not job_id:
            return
        updates: dict[str, Any] = {"total_count": max(0, int(total_count))}
        if current_label:
            updates["current_label"] = current_label
        SyncJob.objects.filter(id=job_id, status=SyncJob.Status.RUNNING).update(
            **updates
        )

    @staticmethod
    def advance(
        *,
        job_id: UUID | str | None,
        processed: int = 1,
        synced: int = 0,
        skipped: int = 0,
        failed: int = 0,
        current_label: str = "",
        lease_owner: str | None = None,
    ) -> None:
        if not job_id:
            return
        updates: dict[str, Any] = {
            "processed_count": F("processed_count") + max(0, int(processed)),
            "synced_count": F("synced_count") + max(0, int(synced)),
            "skipped_count": F("skipped_count") + max(0, int(skipped)),
            "failed_count": F("failed_count") + max(0, int(failed)),
        }
        if current_label:
            updates["current_label"] = current_label
        queryset = SyncJob.objects.filter(id=job_id, status=SyncJob.Status.RUNNING)
        if lease_owner:
            queryset = queryset.filter(lease_owner=lease_owner)
        queryset.update(**updates)

    @staticmethod
    def mark_succeeded(
        *,
        job_id: UUID | str | None,
        result: dict | None = None,
        current_label: str = "Completed",
        lease_owner: str | None = None,
    ) -> None:
        if not job_id:
            return
        queryset = SyncJob.objects.filter(
            id=job_id,
            status__in=(SyncJob.Status.QUEUED, SyncJob.Status.RUNNING),
        )
        if lease_owner:
            queryset = queryset.filter(lease_owner=lease_owner)
        queryset.update(
            status=SyncJob.Status.SUCCEEDED,
            result=result or {},
            current_label=current_label,
            finished_at=timezone.now(),
        )

    @staticmethod
    def mark_failed(
        *,
        job_id: UUID | str | None,
        error: Exception | str,
        current_label: str = "Failed",
        lease_owner: str | None = None,
    ) -> None:
        if not job_id:
            return
        queryset = SyncJob.objects.filter(id=job_id)
        if lease_owner:
            queryset = queryset.filter(lease_owner=lease_owner)
        queryset.exclude(status=SyncJob.Status.SUCCEEDED).update(
            status=SyncJob.Status.FAILED,
            error=str(error)[:4_000],
            current_label=current_label,
            finished_at=timezone.now(),
        )

    @staticmethod
    def claim(
        *,
        job_id: UUID | str | None,
        lease_owner: str,
        lease_seconds: int | None = None,
    ) -> bool:
        if not job_id:
            return False
        now = timezone.now()
        lease_seconds = max(
            30, int(lease_seconds or SyncJobService.DEFAULT_LEASE_SECONDS)
        )
        expires_at = now + timedelta(seconds=lease_seconds)
        updated = (
            SyncJob.objects.filter(
                id=job_id,
                status__in=(SyncJob.Status.QUEUED, SyncJob.Status.RUNNING),
            )
            .filter(
                Q(lease_owner=lease_owner)
                | Q(lease_expires_at__isnull=True)
                | Q(lease_expires_at__lte=now)
            )
            .update(
                status=SyncJob.Status.RUNNING,
                started_at=Coalesce("started_at", Value(now)),
                heartbeat_at=now,
                lease_owner=lease_owner,
                lease_expires_at=expires_at,
                attempt=F("attempt") + 1,
            )
        )
        return bool(updated)

    @staticmethod
    def heartbeat(
        *,
        job_id: UUID | str | None,
        lease_owner: str,
        lease_seconds: int | None = None,
    ) -> bool:
        if not job_id:
            return False
        now = timezone.now()
        lease_seconds = max(
            30, int(lease_seconds or SyncJobService.DEFAULT_LEASE_SECONDS)
        )
        updated = SyncJob.objects.filter(
            id=job_id,
            status=SyncJob.Status.RUNNING,
            lease_owner=lease_owner,
        ).update(
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        return bool(updated)

    @staticmethod
    def release(
        *,
        job_id: UUID | str | None,
        lease_owner: str,
    ) -> None:
        if not job_id:
            return
        SyncJob.objects.filter(
            id=job_id,
            status=SyncJob.Status.RUNNING,
            lease_owner=lease_owner,
        ).update(lease_expires_at=timezone.now())

    @staticmethod
    def stale_running_jobs(*, before: Any | None = None):
        return SyncJob.objects.filter(
            status=SyncJob.Status.RUNNING,
            lease_expires_at__lt=before or timezone.now(),
        )

    @staticmethod
    def get_job(*, job_id: UUID | str) -> SyncJob:
        try:
            return SyncJob.objects.get(id=job_id)
        except SyncJob.DoesNotExist as exc:
            raise SyncJobNotFound() from exc

    @staticmethod
    def list_queryset(
        *,
        status: str | None = None,
        job_type: str | None = None,
    ):
        qs = SyncJob.objects.all()
        if status:
            qs = qs.filter(status=status)
        if job_type:
            qs = qs.filter(job_type=job_type)
        return qs


sync_job_service = SyncJobService()
