from django.db import transaction

from apps.users.models import UserSubject, UserSubjectRatingDetail
from apps.users.selectors.library.rating_detail_selector import (
    UserSubjectRatingDetailSelector,
)


class UserSubjectRatingDetailService:
    @staticmethod
    @transaction.atomic
    def replace_rating_details(*, user, user_subject_id: int, details):
        user_subject = UserSubjectRatingDetailSelector.get_my_subject_or_raise(
            user=user,
            user_subject_id=user_subject_id,
        )
        user_subject = UserSubject.objects.select_for_update().get(pk=user_subject.pk)

        return UserSubjectRatingDetailService.replace_user_subject_rating_details(
            user_subject=user_subject,
            details=details,
        )

    @staticmethod
    @transaction.atomic
    def replace_rating_details_by_subject_id(*, user, subject_id, details):
        user_subject = (
            UserSubjectRatingDetailSelector.get_my_subject_by_subject_id_or_raise(
                user=user,
                subject_id=subject_id,
            )
        )
        user_subject = UserSubject.objects.select_for_update().get(pk=user_subject.pk)

        return UserSubjectRatingDetailService.replace_user_subject_rating_details(
            user_subject=user_subject,
            details=details,
        )

    @staticmethod
    def replace_user_subject_rating_details(*, user_subject, details):
        UserSubjectRatingDetail.objects.filter(
            user_subject=user_subject,
        ).delete()

        UserSubjectRatingDetail.objects.bulk_create(
            [
                UserSubjectRatingDetail(
                    user_subject=user_subject,
                    key=item["key"].strip(),
                    value=item["value"],
                )
                for item in details
            ]
        )

        return UserSubjectRatingDetail.objects.filter(
            user_subject=user_subject
        ).order_by("id")
