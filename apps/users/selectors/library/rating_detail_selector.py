from apps.users.models import UserSubject, UserSubjectRatingDetail
from apps.users.exceptions import UserSubjectNotFound


class UserSubjectRatingDetailSelector:

    @staticmethod
    def get_my_subject(*, user, user_subject_id: int):
        return UserSubject.objects.filter(
            id=user_subject_id,
            user=user,
        ).first()

    @staticmethod
    def get_my_subject_by_subject_id(*, user, subject_id):
        return UserSubject.objects.filter(
            subject_id=subject_id,
            user=user,
        ).first()

    @classmethod
    def get_my_subject_or_raise(cls, *, user, user_subject_id: int):
        user_subject = cls.get_my_subject(
            user=user,
            user_subject_id=user_subject_id,
        )

        if not user_subject:
            raise UserSubjectNotFound()

        return user_subject

    @classmethod
    def get_my_subject_by_subject_id_or_raise(cls, *, user, subject_id):
        user_subject = cls.get_my_subject_by_subject_id(
            user=user,
            subject_id=subject_id,
        )

        if not user_subject:
            raise UserSubjectNotFound()

        return user_subject

    @classmethod
    def list_rating_details(cls, *, user, user_subject_id: int):
        user_subject = cls.get_my_subject_or_raise(
            user=user,
            user_subject_id=user_subject_id,
        )

        return UserSubjectRatingDetail.objects.filter(
            user_subject=user_subject
        ).order_by("id")

    @classmethod
    def list_rating_details_by_subject_id(cls, *, user, subject_id):
        user_subject = cls.get_my_subject_by_subject_id_or_raise(
            user=user,
            subject_id=subject_id,
        )

        return UserSubjectRatingDetail.objects.filter(
            user_subject=user_subject
        ).order_by("id")
