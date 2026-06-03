from django.db.models import Count, Exists, OuterRef, Q

from apps.community.models import CommunityBookmark, CommunityReaction
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

    @staticmethod
    def _is_authenticated_user(user):
        return bool(user and getattr(user, "is_authenticated", False))

    @classmethod
    def _annotate_community_state(cls, qs, *, viewer=None):
        qs = qs.annotate(
            reaction_count=Count(
                "community_reactions",
                filter=Q(
                    community_reactions__reaction_type=CommunityReaction.ReactionType.LIKE
                ),
                distinct=True,
            )
        )

        if not cls._is_authenticated_user(viewer):
            return qs

        return qs.annotate(
            viewer_has_liked=Exists(
                CommunityReaction.objects.filter(
                    user=viewer,
                    review_id=OuterRef("pk"),
                    reaction_type=CommunityReaction.ReactionType.LIKE,
                )
            ),
            viewer_has_bookmarked=Exists(
                CommunityBookmark.objects.filter(
                    user=viewer,
                    review_id=OuterRef("pk"),
                )
            ),
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
        qs = cls._annotate_community_state(qs, viewer=user)

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
        return cls._annotate_community_state(
            cls.base_queryset().filter(
                id=review_id,
                user_subject__user=user,
            ),
            viewer=user,
        ).get()

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

        return cls._annotate_community_state(
            cls.base_queryset().filter(user_subject=user_subject),
            viewer=user,
        ).order_by("-created_at", "-id")

    @classmethod
    def list_public_subject_reviews(cls, *, subject_id, viewer=None):
        return cls._annotate_community_state(cls.base_queryset().filter(
            user_subject__subject_id=subject_id,
            user_subject__is_public=True,
            is_public=True,
        ), viewer=viewer).order_by("-updated_at", "-id")

    @classmethod
    def get_public_review_or_raise(cls, *, review_id: int, viewer=None):
        try:
            return cls._annotate_community_state(
                cls.base_queryset().filter(
                    id=review_id,
                    user_subject__is_public=True,
                    is_public=True,
                ),
                viewer=viewer,
            ).get()
        except Review.DoesNotExist:
            raise ReviewNotFound()
