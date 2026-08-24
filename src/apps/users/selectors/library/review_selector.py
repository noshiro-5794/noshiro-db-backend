from django.db.models import Count, Exists, OuterRef, Q

from apps.community.models import CommunityBookmark, CommunityReaction, UserBlock
from apps.users.exceptions import ReviewNotFound, UserSubjectNotFound
from apps.users.models import Review, UserSubject


class ReviewSelector:
    @staticmethod
    def base_queryset():
        return Review.objects.select_related(
            "user_subject",
            "user_subject__user",
            "user_subject__user__profile",
            "user_subject__entity",
        )

    @staticmethod
    def _is_authenticated_user(user):
        return bool(user and getattr(user, "is_authenticated", False))

    @classmethod
    def _apply_viewer_filters(cls, qs, *, viewer=None):
        if not cls._is_authenticated_user(viewer):
            return qs

        blocked_relationship = UserBlock.objects.filter(
            Q(
                user=viewer,
                blocked_user_id=OuterRef("user_subject__user_id"),
            )
            | Q(
                user_id=OuterRef("user_subject__user_id"),
                blocked_user=viewer,
            )
        )
        return qs.annotate(
            viewer_has_block_relationship=Exists(blocked_relationship)
        ).filter(viewer_has_block_relationship=False)

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
        except Review.DoesNotExist as exc:
            raise ReviewNotFound() from exc

    @classmethod
    def get_my_review_for_update_or_raise(cls, *, user, review_id: int):
        try:
            return (
                cls.base_queryset()
                .select_for_update()
                .get(
                    id=review_id,
                    user_subject__user=user,
                )
            )
        except Review.DoesNotExist as exc:
            raise ReviewNotFound() from exc

    @staticmethod
    def get_my_subject(*, user, user_subject_id: int):
        return (
            UserSubject.objects.select_related("user", "entity")
            .filter(
                id=user_subject_id,
                user=user,
            )
            .first()
        )

    @staticmethod
    def get_my_subject_by_subject_id(*, user, subject_id):
        return (
            UserSubject.objects.select_related("user", "entity")
            .filter(
                entity_id=subject_id,
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
        qs = cls._apply_viewer_filters(
            cls.base_queryset().filter(
                user_subject__entity_id=subject_id,
                user_subject__is_public=True,
                is_public=True,
            ),
            viewer=viewer,
        )
        return cls._annotate_community_state(
            qs,
            viewer=viewer,
        ).order_by("-updated_at", "-id")

    @classmethod
    def get_public_review_or_raise(cls, *, review_id: int, viewer=None):
        try:
            qs = cls._apply_viewer_filters(
                cls.base_queryset().filter(
                    id=review_id,
                    user_subject__is_public=True,
                    is_public=True,
                ),
                viewer=viewer,
            )
            return cls._annotate_community_state(
                qs,
                viewer=viewer,
            ).get()
        except Review.DoesNotExist as exc:
            raise ReviewNotFound() from exc
