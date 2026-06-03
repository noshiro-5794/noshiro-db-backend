from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.community.exceptions import (
    CommunityCommentNotFound,
    CommunityPermissionDenied,
    CommunityTargetLocked,
)
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
    def _decrement_target_reply_count(*, comment):
        if comment.post_id:
            CommunityPost.objects.filter(
                id=comment.post_id,
                reply_count__gt=0,
            ).update(reply_count=F("reply_count") - 1)
        if comment.parent_id:
            CommunityComment.objects.filter(
                id=comment.parent_id,
                reply_count__gt=0,
            ).update(reply_count=F("reply_count") - 1)

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
        if getattr(target, "is_locked", False):
            raise CommunityTargetLocked()

        target_kwargs = cls._target_kwargs(target_type=target_type, target=target)

        parent = None
        if parent_id:
            parent = CommunityComment.objects.filter(
                id=parent_id,
                **target_kwargs,
            ).first()
            if not parent:
                raise CommunityCommentNotFound()
            if parent.is_locked or parent.is_hidden:
                raise CommunityTargetLocked()

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

    @staticmethod
    def _get_my_comment_or_raise(*, author, comment_id: int):
        comment = CommunityComment.objects.filter(id=comment_id).first()
        if not comment:
            raise CommunityCommentNotFound()
        if comment.author_id != author.id:
            raise CommunityPermissionDenied()
        return comment

    @staticmethod
    @transaction.atomic
    def update_comment(*, author, comment_id: int, **fields):
        comment = CommunityCommentService._get_my_comment_or_raise(
            author=author,
            comment_id=comment_id,
        )
        if comment.is_locked or comment.is_hidden:
            raise CommunityTargetLocked()

        allowed_fields = {
            "content",
            "visibility",
            "is_spoiler",
        }
        update_fields = []
        for key, value in fields.items():
            if key not in allowed_fields:
                continue
            setattr(comment, key, value)
            update_fields.append(key)

        if update_fields:
            update_fields.append("updated_at")
            comment.save(update_fields=update_fields)

        return comment

    @staticmethod
    @transaction.atomic
    def delete_comment(*, author, comment_id: int):
        comment = CommunityCommentService._get_my_comment_or_raise(
            author=author,
            comment_id=comment_id,
        )
        if comment.is_locked or comment.is_hidden:
            raise CommunityTargetLocked()

        has_replies = CommunityComment.objects.filter(parent=comment).exists()
        if has_replies:
            comment.content = ""
            comment.is_hidden = True
            comment.is_spoiler = False
            comment.save(
                update_fields=[
                    "content",
                    "is_hidden",
                    "is_spoiler",
                    "updated_at",
                ]
            )
            Activity.objects.filter(comment=comment).update(
                feed_policy=FeedPolicy.HIDDEN
            )
            return

        CommunityCommentService._decrement_target_reply_count(comment=comment)
        comment.delete()

    @staticmethod
    @transaction.atomic
    def hide_comment(*, comment):
        comment.is_hidden = True
        comment.save(update_fields=["is_hidden", "updated_at"])
        Activity.objects.filter(comment=comment).update(feed_policy=FeedPolicy.HIDDEN)
        return comment

    @staticmethod
    @transaction.atomic
    def lock_comment(*, comment):
        comment.is_locked = True
        comment.save(update_fields=["is_locked", "updated_at"])
        return comment
