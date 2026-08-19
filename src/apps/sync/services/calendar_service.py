import logging

from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q

from apps.index.models import (
    AiringEvent,
    CalendarSubject,
    SourceRecord,
    SubjectExternalIdentity,
    Work,
)
from apps.index.services import knowledge_ingestion_service
from apps.sync.models import SyncError
from apps.sync.providers.bangumi import (
    BANGUMI_CALENDAR_NAMESPACE,
    BANGUMI_SUBJECT_NAMESPACE,
    BangumiAPIError,
    bangumi_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.calendar_image_service import calendar_image_service
from apps.sync.services.manual_sync_service import manual_subject_sync_service
from apps.sync.services.source_record_service import source_record_service
from apps.sync.services.subject_service import subject_service
from apps.sync.services.sync_job_service import sync_job_service

logger = logging.getLogger(__name__)


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
        data = bangumi_client.fetch_calendar()
        if not isinstance(data, list):
            raise BangumiAPIError("Bangumi calendar response must be a list.")

        item_count = 0
        synced_subject_count = 0
        failed_subject_count = 0
        detail_synced_count = 0
        detail_failed_count = 0
        calendar_entries_by_subject_id: dict[str, CalendarSubject] = {}
        airing_events: list[AiringEvent] = []
        valid_item_count = cls._count_calendar_items(data)
        if valid_item_count == 0:
            raise BangumiAPIError(
                "Bangumi calendar response did not contain any valid subjects."
            )
        sync_job_service.set_total(
            job_id=job_id,
            total_count=valid_item_count,
            current_label="Syncing calendar subjects",
        )
        for weekday_group in data:
            if not isinstance(weekday_group, dict):
                continue
            weekday = weekday_group.get("weekday") or {}
            if not isinstance(weekday, dict):
                weekday = {}
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
                        logger.info(
                            "Calendar subject sync started",
                            extra={
                                "weekday": weekday.get("en") or "",
                                "bangumi_id": bangumi_id,
                            },
                        )
                    subject = subject_service.upsert_subject(bangumi_id)
                    if subject is None:
                        sync_job_service.advance(
                            job_id=job_id,
                            skipped=1,
                            current_label=f"Skipped calendar subject {bangumi_id}",
                        )
                        if verbose:
                            logger.info(
                                "Calendar subject skipped",
                                extra={"bangumi_id": bangumi_id},
                            )
                        continue
                    calendar_image_url = calendar_image_service.cache_cover(
                        bangumi_id=bangumi_id,
                        images=item.get("images"),
                    )

                    calendar_entries_by_subject_id[str(subject.pk)] = CalendarSubject(
                        subject=subject,
                        weekday_en=weekday.get("en") or "",
                        collection_doing=collection_doing,
                        image_url=calendar_image_url,
                    )
                    work = Work.objects.filter(entity_id=subject.pk).first()
                    if work is not None:
                        weekday_number = cls._weekday_number(weekday)
                        airing_events.append(
                            AiringEvent(
                                work=work,
                                weekday=weekday_number,
                                precision=(
                                    AiringEvent.Precision.WEEKDAY
                                    if weekday_number is not None
                                    else AiringEvent.Precision.UNKNOWN
                                ),
                                raw_value=cls._weekday_raw_value(weekday),
                            )
                        )

                    synced_subject_count += 1
                    sync_job_service.advance(
                        job_id=job_id,
                        synced=1,
                        current_label=f"Prepared calendar subject {bangumi_id}",
                    )
                    if verbose:
                        logger.info(
                            "Calendar subject prepared",
                            extra={"bangumi_id": bangumi_id},
                        )
                except Exception:
                    failed_subject_count += 1
                    logger.exception(
                        "Calendar subject sync failed",
                        extra={"bangumi_id": bangumi_id},
                    )
                    cls._record_error(bangumi_id=bangumi_id)
                    sync_job_service.advance(
                        job_id=job_id,
                        failed=1,
                        current_label=f"Failed calendar subject {bangumi_id}",
                    )
                    if verbose:
                        logger.info(
                            "Calendar subject marked as failed",
                            extra={"bangumi_id": bangumi_id},
                        )

        calendar_entries = list(calendar_entries_by_subject_id.values())
        if item_count and not calendar_entries:
            raise RuntimeError(
                "Calendar refresh produced no valid entries; existing rows were kept."
            )

        with transaction.atomic():
            calendar_recorded = source_record_service.record(
                namespace_spec=BANGUMI_CALENDAR_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id="weekly",
                    payload={"groups": data},
                    canonical_url="https://bgm.tv/calendar",
                    schema_version="bangumi-api-v0",
                    mapper_version="bangumi-calendar-v1",
                ),
            )
            calendar_observation = knowledge_ingestion_service.record_observation(
                provider_record=calendar_recorded.record,
                mapper="bangumi.calendar",
                mapper_version="bangumi-calendar-v1",
                normalized_data={"groups": data},
                schema_name="index.schedule",
                schema_version="1",
            )
            for event in airing_events:
                event.observation = calendar_observation
            cls._replace_calendar(
                calendar_entries=calendar_entries,
                airing_events=airing_events,
            )
        sync_job_service.set_total(
            job_id=job_id,
            total_count=item_count
            + (len(calendar_entries) if sync_subject_details else 0),
            current_label="Calendar rows refreshed",
        )

        if sync_subject_details:
            for calendar_entry in calendar_entries:
                bangumi_id: int | None = None
                try:
                    bangumi_id = manual_subject_sync_service.get_bangumi_subject_id(
                        calendar_entry.subject
                    )
                    if verbose:
                        logger.info(
                            "Calendar subject detail sync started",
                            extra={"bangumi_id": bangumi_id},
                        )
                    manual_subject_sync_service.sync_by_bangumi_id(
                        bangumi_id=bangumi_id,
                    )
                    detail_synced_count += 1
                    sync_job_service.advance(
                        job_id=job_id,
                        current_label=f"Synced calendar subject details {bangumi_id}",
                    )
                    if verbose:
                        logger.info(
                            "Calendar subject detail sync completed",
                            extra={"bangumi_id": bangumi_id},
                        )
                except Exception:
                    detail_failed_count += 1
                    logger.exception(
                        "Calendar subject detail sync failed",
                        extra={
                            "bangumi_id": bangumi_id,
                            "subject_id": str(calendar_entry.subject_id),
                        },
                    )
                    if bangumi_id is not None:
                        cls._record_error(bangumi_id=bangumi_id)
                    sync_job_service.advance(
                        job_id=job_id,
                        failed=1,
                        current_label=(
                            "Failed calendar subject details "
                            f"{bangumi_id or calendar_entry.subject_id}"
                        ),
                    )
                    if verbose:
                        logger.info(
                            "Calendar subject detail marked as failed",
                            extra={"bangumi_id": bangumi_id},
                        )

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
    def _weekday_number(weekday: dict) -> int | None:
        value = weekday.get("id")
        if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 7:
            return value
        name = str(weekday.get("en") or "").strip().lower()[:3]
        return {
            "mon": 1,
            "tue": 2,
            "wed": 3,
            "thu": 4,
            "fri": 5,
            "sat": 6,
            "sun": 7,
        }.get(name)

    @staticmethod
    def _weekday_raw_value(weekday: dict) -> str:
        for key in ("en", "ja", "cn"):
            value = weekday.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:256]
        return ""

    @staticmethod
    @transaction.atomic
    def _replace_calendar(
        *,
        calendar_entries: list[CalendarSubject],
        airing_events: list[AiringEvent],
    ) -> None:
        bangumi_identities = SubjectExternalIdentity.objects.filter(
            subject_id=OuterRef("subject_id"),
            source_record__namespace__provider__slug=(
                BANGUMI_SUBJECT_NAMESPACE.source.slug
            ),
            source_record__namespace__slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        )
        CalendarSubject.objects.annotate(
            has_bangumi_identity=Exists(bangumi_identities),
            has_active_bangumi_identity=Exists(
                bangumi_identities.filter(
                    source_record__status=SourceRecord.Status.ACTIVE
                )
            ),
        ).filter(
            Q(has_active_bangumi_identity=True)
            | Q(
                has_bangumi_identity=False,
                subject__info_source=subject_service.INFO_SOURCE,
            )
        ).delete()
        if calendar_entries:
            CalendarSubject.objects.bulk_create(calendar_entries)
        if airing_events:
            AiringEvent.objects.bulk_create(airing_events, ignore_conflicts=True)

    @classmethod
    def _record_error(cls, *, bangumi_id: int) -> None:
        error, created = SyncError.objects.get_or_create(
            task_name=cls.TASK_NAME,
            entity_id=bangumi_id,
        )
        if not created:
            SyncError.objects.filter(pk=error.pk).update(
                retry_count=F("retry_count") + 1,
            )


calendar_sync_service = CalendarSyncService()
