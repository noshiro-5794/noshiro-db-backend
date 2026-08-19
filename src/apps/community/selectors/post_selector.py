from django.db.models import Exists, F, OuterRef, Q

from apps.community.exceptions import CommunityPostNotFound
from apps.community.models import (
    CommunityBookmark,
    CommunityPost,
    CommunityReaction,
    FeedPolicy,
    UserBlock,
    UserFollow,
    UserMute,
    Visibility,
)


class CommunityPostSelector:
    @staticmethod
    def base_queryset():
        return CommunityPost.objects.select_related(
            "author",
            "author__profile",
            "entity",
            "entity__work",
        ).prefetch_related(
            "entity__names",
            "entity__media__asset",
            "entity__index_memberships__collection",
        )

    @staticmethod
    def _is_authenticated_user(user):
        return bool(user and getattr(user, "is_authenticated", False))

    @classmethod
    def _apply_viewer_filters(cls, qs, *, viewer=None):
        if not cls._is_authenticated_user(viewer):
            return qs

        blocked_author_ids = UserBlock.objects.filter(
            user=viewer,
            blocked_user_id=OuterRef("author_id"),
        )
        blocked_by_author_ids = UserBlock.objects.filter(
            user_id=OuterRef("author_id"),
            blocked_user=viewer,
        )
        muted_author_ids = UserMute.objects.filter(
            user=viewer,
            muted_user_id=OuterRef("author_id"),
        )

        return qs.annotate(
            viewer_has_blocked_author=Exists(blocked_author_ids),
            viewer_is_blocked_by_author=Exists(blocked_by_author_ids),
            viewer_has_muted_author=Exists(muted_author_ids),
        ).filter(
            viewer_has_blocked_author=False,
            viewer_is_blocked_by_author=False,
            viewer_has_muted_author=False,
        )

    @classmethod
    def _annotate_viewer_state(cls, qs, *, viewer=None):
        if not cls._is_authenticated_user(viewer):
            return qs

        return qs.annotate(
            viewer_has_liked=Exists(
                CommunityReaction.objects.filter(
                    user=viewer,
                    post_id=OuterRef("pk"),
                    reaction_type=CommunityReaction.ReactionType.LIKE,
                )
            ),
            viewer_has_bookmarked=Exists(
                CommunityBookmark.objects.filter(
                    user=viewer,
                    post_id=OuterRef("pk"),
                )
            ),
            viewer_is_following_author=Exists(
                UserFollow.objects.filter(
                    follower=viewer,
                    following_id=OuterRef("author_id"),
                )
            ),
        )

    @classmethod
    def list_public_posts(
        cls,
        *,
        entity_id=None,
        keyword=None,
        ordering="-last_activity_at",
        viewer=None,
    ):
        qs = (
            cls.base_queryset()
            .filter(
                visibility=Visibility.PUBLIC,
            )
            .exclude(feed_policy=FeedPolicy.HIDDEN)
        )
        qs = cls._apply_viewer_filters(qs, viewer=viewer)

        if entity_id:
            qs = qs.filter(entity_id=entity_id)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(Q(content__icontains=keyword))

        allowed_ordering = {
            "created_at",
            "-created_at",
            "last_activity_at",
            "-last_activity_at",
            "reaction_count",
            "-reaction_count",
            "reply_count",
            "-reply_count",
        }
        if ordering not in allowed_ordering:
            ordering = "-last_activity_at"

        qs = cls._annotate_viewer_state(qs, viewer=viewer)

        if ordering == "-last_activity_at":
            ordering = F("last_activity_at").desc(nulls_last=True)
        elif ordering == "last_activity_at":
            ordering = F("last_activity_at").asc(nulls_last=True)

        return qs.order_by(ordering, "-id")

    @classmethod
    def get_public_post_or_raise(cls, *, post_id: int, viewer=None):
        post = (
            cls.base_queryset()
            .filter(
                id=post_id,
                visibility=Visibility.PUBLIC,
            )
            .exclude(feed_policy=FeedPolicy.HIDDEN)
        )
        post = cls._apply_viewer_filters(post, viewer=viewer)
        post = cls._annotate_viewer_state(post, viewer=viewer).first()
        if not post:
            raise CommunityPostNotFound()
        return post
