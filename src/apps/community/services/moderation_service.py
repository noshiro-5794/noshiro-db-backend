from django.db import transaction

from apps.community.exceptions import (
    CommunityCommentNotFound,
    CommunityPostNotFound,
)
from apps.community.models import CommunityComment, CommunityPost, ModerationAction
from apps.community.services.comment_service import CommunityCommentService
from apps.community.services.post_service import CommunityPostService


class CommunityModerationService:
    SUPPORTED_ACTION_TYPES = frozenset(
        {
            ModerationAction.ActionType.HIDE,
            ModerationAction.ActionType.LOCK,
        }
    )

    @staticmethod
    def _validate_action_type(action_type: str) -> None:
        if action_type not in CommunityModerationService.SUPPORTED_ACTION_TYPES:
            raise ValueError(f"Unsupported moderation action: {action_type}")

    @staticmethod
    @transaction.atomic
    def moderate_post(
        *,
        moderator,
        post_id: int,
        action_type: str,
        reason: str = "",
    ) -> CommunityPost:
        CommunityModerationService._validate_action_type(action_type)

        post = CommunityPost.objects.select_for_update().filter(id=post_id).first()
        if not post:
            raise CommunityPostNotFound()

        if action_type == ModerationAction.ActionType.HIDE:
            post = CommunityPostService.hide_post(post=post)
        else:
            post = CommunityPostService.lock_post(post=post)

        ModerationAction.objects.create(
            moderator=moderator,
            target_user_id=post.author_id,
            post=post,
            action_type=action_type,
            reason=reason,
        )
        return post

    @staticmethod
    @transaction.atomic
    def moderate_comment(
        *,
        moderator,
        comment_id: int,
        action_type: str,
        reason: str = "",
    ) -> CommunityComment:
        CommunityModerationService._validate_action_type(action_type)

        comment = (
            CommunityComment.objects.select_for_update().filter(id=comment_id).first()
        )
        if not comment:
            raise CommunityCommentNotFound()

        if action_type == ModerationAction.ActionType.HIDE:
            comment = CommunityCommentService.hide_comment(comment=comment)
        else:
            comment = CommunityCommentService.lock_comment(comment=comment)

        ModerationAction.objects.create(
            moderator=moderator,
            target_user_id=comment.author_id,
            comment=comment,
            action_type=action_type,
            reason=reason,
        )
        return comment
