from apps.community.exceptions import (
    CommunityInteractionBlocked,
    CommunityTargetInvalid,
    CommunityTargetNotFound,
)
from apps.community.models import (
    CommunityComment,
    CommunityPost,
    FeedPolicy,
    Visibility,
)
from apps.community.selectors.activity_selector import ActivitySelector
from apps.community.selectors.relationship_selector import UserRelationshipSelector
from apps.users.models import Collection, Review


class CommunityTargetSelector:
    REACTION_TARGETS = {"post", "comment", "review", "collection", "activity"}
    BOOKMARK_TARGETS = {"post", "review", "collection"}
    REPORT_TARGETS = {"post", "comment", "review", "collection", "activity"}
    COMMENT_TARGETS = {"post", "review", "collection", "activity"}

    @staticmethod
    def _raise_if_not_allowed(*, target_type: str, allowed_targets: set[str]):
        if target_type not in allowed_targets:
            raise CommunityTargetInvalid()

    @staticmethod
    def _get_public_post(target_id):
        return (
            CommunityPost.objects.select_related("author", "author__profile")
            .filter(
                id=target_id,
                visibility=Visibility.PUBLIC,
            )
            .exclude(feed_policy=FeedPolicy.HIDDEN)
            .first()
        )

    @staticmethod
    def _get_public_comment(target_id):
        return (
            CommunityComment.objects.select_related("author", "author__profile")
            .filter(
                id=target_id,
                visibility=Visibility.PUBLIC,
                is_hidden=False,
            )
            .first()
        )

    @staticmethod
    def _get_public_review(target_id):
        return (
            Review.objects.select_related(
                "user_subject",
                "user_subject__user",
                "user_subject__user__profile",
                "user_subject__subject",
            )
            .filter(
                id=target_id,
                is_public=True,
                user_subject__is_public=True,
            )
            .first()
        )

    @staticmethod
    def _get_public_collection(target_id):
        return (
            Collection.objects.select_related("user", "user__profile")
            .filter(
                id=target_id,
                is_public=True,
            )
            .first()
        )

    @staticmethod
    def _get_public_activity(target_id):
        return (
            ActivitySelector.base_queryset()
            .filter(id=target_id)
            .filter(ActivitySelector.public_visibility_filter())
            .first()
        )

    @classmethod
    def get_target_or_raise(
        cls,
        *,
        target_type: str,
        target_id: int,
        allowed_targets: set[str],
        actor=None,
    ):
        cls._raise_if_not_allowed(
            target_type=target_type,
            allowed_targets=allowed_targets,
        )

        getters = {
            "post": cls._get_public_post,
            "comment": cls._get_public_comment,
            "review": cls._get_public_review,
            "collection": cls._get_public_collection,
            "activity": cls._get_public_activity,
        }
        target = getters[target_type](target_id)

        if not target:
            raise CommunityTargetNotFound()

        owner = cls.owner_for_target(target)
        if (
            actor
            and owner
            and actor.pk != owner.pk
            and UserRelationshipSelector.is_blocked_between(
                user=actor,
                target_user=owner,
            )
        ):
            raise CommunityInteractionBlocked()

        return target

    @staticmethod
    def owner_for_target(target):
        if isinstance(target, (CommunityPost, CommunityComment)):
            return target.author
        if isinstance(target, Review):
            return target.user_subject.user
        if isinstance(target, Collection):
            return target.user
        return getattr(target, "user", None)
