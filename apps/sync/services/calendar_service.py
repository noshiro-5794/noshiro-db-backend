from django.db import transaction

from apps.index.models import CalendarSubject
from apps.sync.models import SyncError
from apps.sync.providers.bangumi import bangumi_client
from apps.sync.services.calendar_image_service import calendar_image_service
from apps.sync.services.manual_sync_service import manual_subject_sync_service
from apps.sync.services.rate_limiter import rate_limiter
from apps.sync.services.subject_service import subject_service
from apps.sync.services.sync_job_service import sync_job_service


class CalendarSyncService:

    TASK_NAME = "calendar"

    @classmethod
    def sync_calendar(
        cls,
        *,
        sync_subject_details: bool = True,
        job_id: str | None = None,
        verbose: bool = False,
    ) -> dict:
        sync_job_service.mark_running(
            job_id=job_id,
            total_count=0,
            current_label="Fetching calendar",
        )
        rate_limiter.acquire()
        data = bangumi_client.fetch_calendar()
        if not isinstance(data, list):
            result = {
                "weekday_count": 0,
                "item_count": 0,
                "synced_subject_count": 0,
                "failed_subject_count": 0,
            }
            sync_job_service.mark_succeeded(
                job_id=job_id,
                result=result,
                current_label="Calendar sync completed",
            )
            return result

        item_count = 0
        synced_subject_count = 0
        failed_subject_count = 0
        detail_synced_count = 0
        detail_failed_count = 0
        calendar_entries = []
        valid_item_count = cls._count_calendar_items(data)
        sync_job_service.set_total(
            job_id=job_id,
            total_count=valid_item_count,
            current_label="Syncing calendar subjects",
        )

        for weekday_group in data:
            if not isinstance(weekday_group, dict):
                continue
            weekday = weekday_group.get("weekday") or {}
            items = weekday_group.get("items") or []
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                bangumi_id = item.get("id")
                if not isinstance(bangumi_id, int):
                    continue
                collection = item.get("collection") or {}
                doing = collection.get("doing") if isinstance(collection, dict) else 0
                collection_doing = doing if isinstance(doing, int) and doing >= 0 else 0

                item_count += 1
                try:
                    if verbose:
                        print(
                            f"[calendar] {weekday.get('en') or ''} {bangumi_id}: start",
                            flush=True,
                        )
                    rate_limiter.acquire()
                    subject = subject_service.upsert_subject(bangumi_id)
                    if subject is None:
                        sync_job_service.advance(
                            job_id=job_id,
                            skipped=1,
                            current_label=f"Skipped calendar subject {bangumi_id}",
                        )
                        if verbose:
                            print(f"[calendar] {bangumi_id}: skipped", flush=True)
                        continue
                    calendar_image_url = calendar_image_service.cache_cover(
                        bangumi_id=bangumi_id,
                        images=item.get("images"),
                        verbose=verbose,
                    )

                    calendar_entries.append(
                        CalendarSubject(
                            subject=subject,
                            weekday_en=weekday.get("en") or "",
                            collection_doing=collection_doing,
                            image_url=calendar_image_url,
                        )
                    )

                    synced_subject_count += 1
                    sync_job_service.advance(
                        job_id=job_id,
                        synced=1,
                        current_label=f"Prepared calendar subject {bangumi_id}",
                    )
                    if verbose:
                        print(f"[calendar] {bangumi_id}: prepared", flush=True)
                except Exception:
                    failed_subject_count += 1
                    cls._record_error(bangumi_id=bangumi_id)
                    sync_job_service.advance(
                        job_id=job_id,
                        failed=1,
                        current_label=f"Failed calendar subject {bangumi_id}",
                    )
                    if verbose:
                        print(f"[calendar] {bangumi_id}: failed", flush=True)

        cls._replace_calendar(calendar_entries=calendar_entries)
        sync_job_service.set_total(
            job_id=job_id,
            total_count=item_count + (len(calendar_entries) if sync_subject_details else 0),
            current_label="Calendar rows refreshed",
        )

        if sync_subject_details:
            for calendar_entry in calendar_entries:
                bangumi_id = calendar_entry.subject.id_source
                try:
                    if verbose:
                        print(f"[calendar-detail] {bangumi_id}: start", flush=True)
                    manual_subject_sync_service.sync_by_bangumi_id(
                        bangumi_id=bangumi_id,
                    )
                    detail_synced_count += 1
                    sync_job_service.advance(
                        job_id=job_id,
                        current_label=f"Synced calendar subject details {bangumi_id}",
                    )
                    if verbose:
                        print(f"[calendar-detail] {bangumi_id}: synced", flush=True)
                except Exception:
                    detail_failed_count += 1
                    cls._record_error(bangumi_id=bangumi_id)
                    sync_job_service.advance(
                        job_id=job_id,
                        failed=1,
                        current_label=f"Failed calendar subject details {bangumi_id}",
                    )
                    if verbose:
                        print(f"[calendar-detail] {bangumi_id}: failed", flush=True)

        result = {
            "weekday_count": len(data),
            "item_count": item_count,
            "synced_subject_count": synced_subject_count,
            "failed_subject_count": failed_subject_count,
            "detail_synced_count": detail_synced_count,
            "detail_failed_count": detail_failed_count,
        }
        sync_job_service.mark_succeeded(
            job_id=job_id,
            result=result,
            current_label="Calendar sync completed",
        )
        return result

    @staticmethod
    def _count_calendar_items(data: list) -> int:
        total = 0
        for weekday_group in data:
            if not isinstance(weekday_group, dict):
                continue
            items = weekday_group.get("items") or []
            if not isinstance(items, list):
                continue
            total += sum(
                1
                for item in items
                if isinstance(item, dict) and isinstance(item.get("id"), int)
            )
        return total

    @staticmethod
    @transaction.atomic
    def _replace_calendar(*, calendar_entries: list[CalendarSubject]) -> None:
        CalendarSubject.objects.all().delete()
        if calendar_entries:
            CalendarSubject.objects.bulk_create(
                calendar_entries,
                ignore_conflicts=True,
            )

    @classmethod
    def _record_error(cls, *, bangumi_id: int) -> None:
        error, created = SyncError.objects.get_or_create(
            task_name=cls.TASK_NAME,
            entity_id=bangumi_id,
        )
        if not created:
            error.retry_count += 1
            error.save(update_fields=["retry_count", "last_occurred_at"])


calendar_sync_service = CalendarSyncService()
