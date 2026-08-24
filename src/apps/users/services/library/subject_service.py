from datetime import date
from typing import Any

from django.db import transaction

from apps.community.services.activity_service import ActivityService
from apps.index.constants import PRIMARY_SUBJECT_TYPES
from apps.index.exceptions import SubjectNotFound, SubjectTypeNotSupported
from apps.index.models import Entity
from apps.users.exceptions import InvalidWatchDateRange
from apps.users.models import UserSubject
from apps.users.selectors.library.subject_selector import SubjectSelector


class UserSubjectService:
    @staticmethod
    def _normalize_watch_date(value: date | str | None) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise InvalidWatchDateRange() from exc

    @staticmethod
    def _validate_watch_date_range(
        *,
        watch_start_date: date | None,
        watch_end_date: date | None,
    ) -> None:
        if watch_start_date and watch_end_date and watch_start_date > watch_end_date:
            raise InvalidWatchDateRange()

    @staticmethod
    @transaction.atomic
    def add_subject(
        *,
        user,
        subject_id,
        status,
        simple_rating=None,
        rating=None,
        comment="",
        watch_start_date=None,
        watch_end_date=None,
        is_public: bool = True,
    ) -> tuple[UserSubject, bool]:
        try:
            entity = Entity.objects.select_related("work").get(pk=subject_id)
        except Entity.DoesNotExist as exc:
            raise SubjectNotFound() from exc

        if (
            entity.kind != Entity.Kind.WORK
            or not hasattr(entity, "work")
            or entity.work.work_type not in PRIMARY_SUBJECT_TYPES
        ):
            raise SubjectTypeNotSupported()

        watch_start_date = UserSubjectService._normalize_watch_date(watch_start_date)
        watch_end_date = UserSubjectService._normalize_watch_date(watch_end_date)
        UserSubjectService._validate_watch_date_range(
            watch_start_date=watch_start_date,
            watch_end_date=watch_end_date,
        )

        user_subject, created = UserSubject.objects.update_or_create(
            user=user,
            entity=entity,
            defaults={
                "status": status,
                "simple_rating": simple_rating,
                "rating": rating,
                "comment": comment,
                "watch_start_date": watch_start_date,
                "watch_end_date": watch_end_date,
                "is_public": is_public,
            },
        )

        if created:
            ActivityService.create_user_subject_created_activity(
                user=user,
                user_subject=user_subject,
            )
        else:
            ActivityService.create_user_subject_updated_activity(
                user=user,
                user_subject=user_subject,
            )

        return user_subject, created

    @staticmethod
    @transaction.atomic
    def update_subject(*, user, user_subject_id: int, **fields: Any) -> UserSubject:
        user_subject = SubjectSelector.get_user_subject_for_update_or_raise(
            user=user,
            user_subject_id=user_subject_id,
        )
        allowed_fields = {
            "status",
            "simple_rating",
            "rating",
            "comment",
            "watch_start_date",
            "watch_end_date",
            "is_public",
        }
        update_fields = []

        for key, value in fields.items():
            if key in allowed_fields:
                if key in {"watch_start_date", "watch_end_date"}:
                    value = UserSubjectService._normalize_watch_date(value)
                setattr(user_subject, key, value)
                update_fields.append(key)
        UserSubjectService._validate_watch_date_range(
            watch_start_date=user_subject.watch_start_date,
            watch_end_date=user_subject.watch_end_date,
        )
        if update_fields:
            update_fields.append("updated_at")
            user_subject.save(update_fields=update_fields)
            ActivityService.create_user_subject_updated_activity(
                user=user,
                user_subject=user_subject,
            )
        return user_subject

    @staticmethod
    @transaction.atomic
    def delete_subject(*, user, user_subject_id: int) -> None:
        user_subject = SubjectSelector.get_user_subject_for_update_or_raise(
            user=user,
            user_subject_id=user_subject_id,
        )
        user_subject.delete()
