from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

from apps.community.models import (
    CommunityBookmark,
    CommunityReaction,
    UserBlock,
    UserFollow,
)
from apps.users.exceptions import UserNotFound
from apps.users.models import (
    Collection,
    CollectionItem,
    Review,
    UserSubject,
)

User = get_user_model()


class PublicProfileSelector:
    @staticmethod
    def _count_subquery(queryset, *, group_by: str):
        return Coalesce(
            Subquery(
                queryset.order_by()
                .values(group_by)
                .annotate(total=Count("pk"))
                .values("total")[:1],
                output_field=IntegerField(),
            ),
            Value(0),
        )

    @staticmethod
    def _is_authenticated_user(user):
        return bool(user and getattr(user, "is_authenticated", False))

    @classmethod
    def _raise_if_blocked(cls, *, user, viewer=None) -> None:
        if not cls._is_authenticated_user(viewer) or viewer.pk == user.pk:
            return

        is_blocked = UserBlock.objects.filter(
            Q(user=viewer, blocked_user=user) | Q(user=user, blocked_user=viewer)
        ).exists()
        if is_blocked:
            raise UserNotFound()

    @classmethod
    def _annotate_review_community_state(cls, qs, *, viewer=None):
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
    def _annotate_collection_community_state(cls, qs, *, viewer=None):
        qs = qs.annotate(
            item_count=Count("items", distinct=True),
            reaction_count=Count(
                "community_reactions",
                filter=Q(
                    community_reactions__reaction_type=CommunityReaction.ReactionType.LIKE
                ),
                distinct=True,
            ),
        )

        if not cls._is_authenticated_user(viewer):
            return qs

        return qs.annotate(
            viewer_has_liked=Exists(
                CommunityReaction.objects.filter(
                    user=viewer,
                    collection_id=OuterRef("pk"),
                    reaction_type=CommunityReaction.ReactionType.LIKE,
                )
            ),
            viewer_has_bookmarked=Exists(
                CommunityBookmark.objects.filter(
                    user=viewer,
                    collection_id=OuterRef("pk"),
                )
            ),
        )

    @staticmethod
    def get_user_by_id(*, user_id: int):
        return User.objects.select_related("profile").filter(id=user_id).first()

    @classmethod
    def get_user_by_id_or_raise(cls, *, user_id: int, viewer=None):
        user = cls.get_user_by_id(user_id=user_id)

        if not user:
            raise UserNotFound()

        cls._raise_if_blocked(user=user, viewer=viewer)
        return user

    @classmethod
    def get_public_profile(cls, *, target_user_id: int, viewer=None):
        public_subject_count = cls._count_subquery(
            UserSubject.objects.filter(
                user_id=OuterRef("pk"),
                is_public=True,
            ),
            group_by="user_id",
        )
        public_review_count = cls._count_subquery(
            Review.objects.filter(
                user_subject__user_id=OuterRef("pk"),
                user_subject__is_public=True,
                is_public=True,
            ),
            group_by="user_subject__user_id",
        )
        collection_count = cls._count_subquery(
            Collection.objects.filter(
                user_id=OuterRef("pk"),
                is_public=True,
            ),
            group_by="user_id",
        )
        following_count = cls._count_subquery(
            UserFollow.objects.filter(follower_id=OuterRef("pk")),
            group_by="follower_id",
        )
        follower_count = cls._count_subquery(
            UserFollow.objects.filter(following_id=OuterRef("pk")),
            group_by="following_id",
        )
        user_qs = (
            User.objects.select_related("profile")
            .filter(id=target_user_id)
            .annotate(
                public_subject_count=public_subject_count,
                public_review_count=public_review_count,
                collection_count=collection_count,
                following_count=following_count,
                follower_count=follower_count,
            )
        )

        user = user_qs.first()

        if not user:
            raise UserNotFound()

        cls._raise_if_blocked(user=user, viewer=viewer)

        if viewer and viewer.is_authenticated:
            user.is_following = UserFollow.objects.filter(
                follower=viewer,
                following=user,
            ).exists()
        else:
            user.is_following = False

        return user

    @staticmethod
    def list_public_user_subjects(
        *,
        user,
        status=None,
        subject_type=None,
        keyword=None,
        ordering="-id",
    ):
        qs = UserSubject.objects.select_related("user", "subject").filter(
            user=user,
            is_public=True,
        )

        if status:
            qs = qs.filter(status=status)

        if subject_type:
            qs = qs.filter(subject__subject_type=subject_type)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(
                    Q(subject__title__icontains=keyword)
                    | Q(subject__title_cn__icontains=keyword)
                    | Q(comment__icontains=keyword)
                )

        allowed_ordering = {
            "id",
            "-id",
            "simple_rating",
            "-simple_rating",
            "rating",
            "-rating",
            "watch_start_date",
            "-watch_start_date",
            "watch_end_date",
            "-watch_end_date",
        }

        if ordering not in allowed_ordering:
            ordering = "-id"

        return qs.order_by(ordering, "-id")

    @classmethod
    def list_public_reviews(
        cls,
        *,
        user,
        keyword=None,
        ordering="-id",
        viewer=None,
    ):
        qs = Review.objects.select_related(
            "user_subject",
            "user_subject__user",
            "user_subject__subject",
        ).filter(
            user_subject__user=user,
            user_subject__is_public=True,
        )

        qs = cls._annotate_review_community_state(
            qs.filter(is_public=True),
            viewer=viewer,
        )

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(
                    Q(title__icontains=keyword) | Q(content__icontains=keyword)
                )

        allowed_ordering = {
            "id",
            "-id",
        }

        allowed_ordering.update(
            {
                "created_at",
                "-created_at",
            }
        )

        if ordering not in allowed_ordering:
            ordering = "-id"

        return qs.order_by(ordering, "-id")

    @classmethod
    def list_public_collections(
        cls,
        *,
        user,
        keyword=None,
        ordering="-id",
        viewer=None,
    ):
        qs = Collection.objects.filter(
            user=user,
            is_public=True,
        )
        qs = cls._annotate_collection_community_state(qs, viewer=viewer)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(Q(name__icontains=keyword) | Q(note__icontains=keyword))

        allowed_ordering = {
            "id",
            "-id",
            "name",
            "-name",
            "simple_rating",
            "-simple_rating",
            "item_count",
            "-item_count",
        }

        if ordering not in allowed_ordering:
            ordering = "-id"

        return qs.order_by(ordering, "-id")

    @classmethod
    def get_public_collection(cls, *, user, collection_id: int, viewer=None):
        return cls._annotate_collection_community_state(
            Collection.objects.filter(
                user=user,
                id=collection_id,
                is_public=True,
            ),
            viewer=viewer,
        ).first()

    @staticmethod
    def list_public_collection_items(*, collection):
        return (
            CollectionItem.objects.select_related(
                "collection",
                "user_subject",
                "user_subject__subject",
            )
            .filter(
                collection=collection,
                user_subject__is_public=True,
            )
            .order_by("order", "id")
        )
