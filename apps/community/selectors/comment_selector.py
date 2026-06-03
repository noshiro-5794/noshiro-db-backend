from django.db.models import Exists, OuterRef, Q

from apps.community.models import CommunityComment, Visibility
from apps.community.selectors.target_selector import CommunityTargetSelector
from apps.community.models import CommunityReaction, UserBlock, UserFollow, UserMute


class CommunityCommentSelector:

    @staticmethod
    def base_queryset():
        return CommunityComment.objects.select_related(
            "author",
            "author__profile",
            "post",
            "review",
            "collection",
            "activity",
            "parent",
        )

    @staticmethod
    def _is_authenticated_user(user):
        return bool(user and getattr(user, "is_authenticated", False))

    @classmethod
    def _apply_viewer_filters(cls, qs, *, viewer=None):
        if not cls._is_authenticated_user(viewer):
            return qs

        return (
            qs.annotate(
                viewer_has_blocked_author=Exists(
                    UserBlock.objects.filter(
                        user=viewer,
                        blocked_user_id=OuterRef("author_id"),
                    )
                ),
                viewer_is_blocked_by_author=Exists(
                    UserBlock.objects.filter(
                        user_id=OuterRef("author_id"),
                        blocked_user=viewer,
                    )
                ),
                viewer_has_muted_author=Exists(
                    UserMute.objects.filter(
                        user=viewer,
                        muted_user_id=OuterRef("author_id"),
                    )
                ),
            )
            .filter(
                viewer_has_blocked_author=False,
                viewer_is_blocked_by_author=False,
                viewer_has_muted_author=False,
            )
        )

    @classmethod
    def _annotate_viewer_state(cls, qs, *, viewer=None):
        if not cls._is_authenticated_user(viewer):
            return qs

        return qs.annotate(
            viewer_has_liked=Exists(
                CommunityReaction.objects.filter(
                    user=viewer,
                    comment_id=OuterRef("pk"),
                    reaction_type=CommunityReaction.ReactionType.LIKE,
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
    def list_public_comments(cls, *, target_type: str, target_id: int, viewer=None):
        target = CommunityTargetSelector.get_target_or_raise(
            target_type=target_type,
            target_id=target_id,
            allowed_targets=CommunityTargetSelector.COMMENT_TARGETS,
        )

        qs = cls.base_queryset().filter(
            **{target_type: target},
            visibility=Visibility.PUBLIC,
        ).filter(Q(is_hidden=False) | Q(reply_count__gt=0))
        qs = cls._apply_viewer_filters(qs, viewer=viewer)
        qs = cls._annotate_viewer_state(qs, viewer=viewer)

        return qs.order_by("created_at", "id")

    @classmethod
    def list_public_post_comments(cls, *, post, viewer=None):
        return cls.list_public_comments(
            target_type="post",
            target_id=post.id,
            viewer=viewer,
        )
