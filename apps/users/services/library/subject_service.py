from django.db import transaction

from apps.index.constants import PRIMARY_SUBJECT_TYPES
from apps.index.exceptions import SubjectNotFound, SubjectTypeNotSupported
from apps.index.models import Subject
from apps.users.models import UserSubject
from apps.users.exceptions import UserSubjectNotFound
from apps.users.selectors.library.subject_selector import SubjectSelector
from apps.community.services.activity_service import ActivityService


class UserSubjectService:

    @staticmethod
    def _normalize_watch_date(value) -> str:
        if not value:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

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
        watch_start_date="",
        watch_end_date="",
        is_public=True,
    ) -> UserSubject:
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            raise SubjectNotFound()

        if subject.subject_type not in PRIMARY_SUBJECT_TYPES:
            raise SubjectTypeNotSupported()

        watch_start_date = UserSubjectService._normalize_watch_date(watch_start_date)
        watch_end_date = UserSubjectService._normalize_watch_date(watch_end_date)

        user_subject, created = UserSubject.objects.update_or_create(
            user=user,
            subject=subject,
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
    def update_subject(*, user, user_subject_id: int, **fields) -> UserSubject:
        try:
            user_subject = SubjectSelector.get_user_subject(
                user=user, user_subject_id=user_subject_id
            )
        except UserSubject.DoesNotExist:
            raise UserSubjectNotFound()
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
        try:
            user_subject = SubjectSelector.get_user_subject(
                user=user, user_subject_id=user_subject_id
            )
        except UserSubject.DoesNotExist:
            raise UserSubjectNotFound()
        user_subject.delete()
