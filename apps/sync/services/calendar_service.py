from django.db import transaction

from apps.index.models import CalendarSubject
from apps.sync.models import SyncError
from apps.sync.providers.bangumi import bangumi_client
from apps.sync.services.manual_sync_service import manual_subject_sync_service
from apps.sync.services.rate_limiter import rate_limiter
from apps.sync.services.subject_service import subject_service


class CalendarSyncService:

    TASK_NAME = "calendar"

    @classmethod
    def sync_calendar(
        cls,
        *,
        sync_subject_details: bool = True,
        verbose: bool = False,
    ) -> dict:
        rate_limiter.acquire()
        data = bangumi_client.fetch_calendar()
        if not isinstance(data, list):
            return {
                "weekday_count": 0,
                "item_count": 0,
                "synced_subject_count": 0,
                "failed_subject_count": 0,
            }

        item_count = 0
        synced_subject_count = 0
        failed_subject_count = 0
        calendar_entries = []

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
                        if verbose:
                            print(f"[calendar] {bangumi_id}: skipped", flush=True)
                        continue

                    calendar_entries.append(
                        CalendarSubject(
                            subject=subject,
                            weekday_en=weekday.get("en") or "",
                            collection_doing=collection_doing,
                        )
                    )

                    if sync_subject_details:
                        manual_subject_sync_service.sync_by_bangumi_id(
                            bangumi_id=bangumi_id,
                        )
                    synced_subject_count += 1
                    if verbose:
                        print(f"[calendar] {bangumi_id}: synced", flush=True)
                except Exception:
                    failed_subject_count += 1
                    cls._record_error(bangumi_id=bangumi_id)
                    if verbose:
                        print(f"[calendar] {bangumi_id}: failed", flush=True)

        cls._replace_calendar(calendar_entries=calendar_entries)

        return {
            "weekday_count": len(data),
            "item_count": item_count,
            "synced_subject_count": synced_subject_count,
            "failed_subject_count": failed_subject_count,
        }

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
