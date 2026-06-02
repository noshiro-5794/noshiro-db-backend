from django.db.models import Q

from apps.users.models import Review, UserSubject
from apps.users.exceptions import UserSubjectNotFound, ReviewNotFound


class ReviewSelector:

    @staticmethod
    def base_queryset():
        return Review.objects.select_related(
            "user_subject",
            "user_subject__user",
            "user_subject__subject",
        )

    @classmethod
    def list_my_reviews(
        cls,
        *,
        user,
        keyword=None,
        ordering="-created_at",
    ):
        qs = cls.base_queryset().filter(
            user_subject__user=user,
        )

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(
                    Q(title__icontains=keyword) | Q(content__icontains=keyword)
                )

        allowed_ordering = {
            "created_at",
            "-created_at",
            "id",
            "-id",
        }

        if ordering not in allowed_ordering:
            ordering = "-created_at"

        return qs.order_by(ordering, "-id")

    @classmethod
    def get_my_review(cls, *, user, review_id: int):
        return cls.base_queryset().get(
            id=review_id,
            user_subject__user=user,
        )

    @classmethod
    def get_my_review_or_raise(cls, *, user, review_id: int):
        try:
            return cls.get_my_review(
                user=user,
                review_id=review_id,
            )
        except Review.DoesNotExist:
            raise ReviewNotFound()

    @staticmethod
    def get_my_subject(*, user, user_subject_id: int):
        return (
            UserSubject.objects.select_related("user", "subject")
            .filter(
                id=user_subject_id,
                user=user,
            )
            .first()
        )

    @staticmethod
    def get_my_subject_by_subject_id(*, user, subject_id):
        return (
            UserSubject.objects.select_related("user", "subject")
            .filter(
                subject_id=subject_id,
                user=user,
            )
            .first()
        )

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
    def list_my_subject_reviews_by_subject_id(cls, *, user, subject_id):
        user_subject = cls.get_my_subject_by_subject_id_or_raise(
            user=user,
            subject_id=subject_id,
        )

        return cls.base_queryset().filter(user_subject=user_subject).order_by(
            "-created_at", "-id"
        )

    @classmethod
    def list_public_subject_reviews(cls, *, subject_id):
        return cls.base_queryset().filter(
            user_subject__subject_id=subject_id,
            user_subject__is_public=True,
            is_public=True,
        ).order_by("-updated_at", "-id")

    @classmethod
    def get_public_review_or_raise(cls, *, review_id: int):
        try:
            return cls.base_queryset().get(
                id=review_id,
                user_subject__is_public=True,
                is_public=True,
            )
        except Review.DoesNotExist:
            raise ReviewNotFound()
