from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.community.exceptions import CommunityCommentNotFound
from apps.community.models import (
    Activity,
    CommunityComment,
    CommunityPost,
    FeedPolicy,
    Visibility,
)
from apps.community.selectors.target_selector import CommunityTargetSelector
from apps.community.services.notification_service import NotificationService
from apps.users.models import Collection, Review


class CommunityCommentService:

    @staticmethod
    def _target_kwargs(*, target_type: str, target):
        return {target_type: target}

    @staticmethod
    def _owner_for_target(target):
        if isinstance(target, CommunityPost):
            return target.author
        if isinstance(target, Review):
            return target.user_subject.user
        if isinstance(target, Collection):
            return target.user
        if isinstance(target, Activity):
            return target.user
        return None

    @staticmethod
    def _subject_for_target(target):
        if isinstance(target, CommunityPost):
            return target.subject
        if isinstance(target, Review):
            return target.user_subject.subject
        if isinstance(target, Activity):
            return target.subject
        return None

    @staticmethod
    def _notification_kwargs(*, target_type: str, target):
        if target_type in {"post", "review", "collection"}:
            return {target_type: target}
        return {}

    @staticmethod
    def _bump_target_reply_count(*, target_type: str, target):
        if target_type == "post":
            CommunityPost.objects.filter(id=target.id).update(
                reply_count=F("reply_count") + 1,
                last_activity_at=timezone.now(),
            )

    @staticmethod
    def _activity_kwargs(*, target_type: str, target):
        if target_type in {"post", "review", "collection"}:
            return {target_type: target}
        return {}

    @classmethod
    @transaction.atomic
    def create_comment(
        cls,
        *,
        author,
        target_type: str,
        target_id: int,
        content: str,
        parent_id=None,
        visibility=Visibility.PUBLIC,
        is_spoiler=False,
    ) -> CommunityComment:
        target = CommunityTargetSelector.get_target_or_raise(
            target_type=target_type,
            target_id=target_id,
            allowed_targets=CommunityTargetSelector.COMMENT_TARGETS,
        )
        target_kwargs = cls._target_kwargs(target_type=target_type, target=target)

        parent = None
        if parent_id:
            parent = CommunityComment.objects.filter(
                id=parent_id,
                **target_kwargs,
            ).first()
            if not parent:
                raise CommunityCommentNotFound()

        comment = CommunityComment.objects.create(
            author=author,
            parent=parent,
            content=content,
            visibility=visibility,
            is_spoiler=is_spoiler,
            **target_kwargs,
        )

        cls._bump_target_reply_count(target_type=target_type, target=target)
        if parent:
            CommunityComment.objects.filter(id=parent.id).update(
                reply_count=F("reply_count") + 1
            )

        activity = Activity.objects.create(
            user=author,
            subject=cls._subject_for_target(target),
            comment=comment,
            activity_type=Activity.ActivityType.COMMENT_CREATED,
            message=f"Commented on a {target_type}",
            visibility=visibility,
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"{target_type}_comment:{target.id}",
            dedupe_key=f"comment_created:{comment.id}",
            metadata={
                "target": {
                    "type": target_type,
                    "id": target.id,
                },
                "comment": {"id": comment.id},
            },
            **cls._activity_kwargs(target_type=target_type, target=target),
        )
        NotificationService.create_commented_notification(
            recipient=cls._owner_for_target(target),
            actor=author,
            activity=activity,
            comment=comment,
            **cls._notification_kwargs(target_type=target_type, target=target),
        )

        return comment

    @staticmethod
    @transaction.atomic
    def create_post_comment(
        *,
        author,
        post: CommunityPost,
        content: str,
        parent_id=None,
        visibility=Visibility.PUBLIC,
        is_spoiler=False,
    ) -> CommunityComment:
        return CommunityCommentService.create_comment(
            author=author,
            target_type="post",
            target_id=post.id,
            content=content,
            parent_id=parent_id,
            visibility=visibility,
            is_spoiler=is_spoiler,
        )
