from unittest.mock import Mock, patch

import pytest

from apps.community.exceptions import (
    CommunityCommentNotFound,
    CommunityPostNotFound,
)
from apps.community.models import ModerationAction
from apps.community.services.moderation_service import CommunityModerationService


@patch("apps.community.services.moderation_service.ModerationAction.objects.create")
@patch("apps.community.services.moderation_service.CommunityPostService.hide_post")
@patch(
    "apps.community.services.moderation_service.CommunityPost.objects.select_for_update"
)
def test_moderate_post_hides_post_and_records_action(
    select_posts_for_update: Mock,
    hide_post: Mock,
    create_action: Mock,
) -> None:
    moderator = Mock()
    post = Mock(id=1, author_id=2)
    filter_posts = select_posts_for_update.return_value.filter
    filter_posts.return_value.first.return_value = post
    hide_post.return_value = post

    result = CommunityModerationService.moderate_post.__wrapped__(
        moderator=moderator,
        post_id=post.id,
        action_type=ModerationAction.ActionType.HIDE,
        reason="Spam",
    )

    assert result is post
    select_posts_for_update.assert_called_once_with()
    filter_posts.assert_called_once_with(id=post.id)
    hide_post.assert_called_once_with(post=post)
    create_action.assert_called_once_with(
        moderator=moderator,
        target_user_id=post.author_id,
        post=post,
        action_type=ModerationAction.ActionType.HIDE,
        reason="Spam",
    )


@patch("apps.community.services.moderation_service.ModerationAction.objects.create")
@patch(
    "apps.community.services.moderation_service.CommunityCommentService.lock_comment"
)
@patch(
    "apps.community.services.moderation_service.CommunityComment.objects.select_for_update"
)
def test_moderate_comment_locks_comment_and_records_action(
    select_comments_for_update: Mock,
    lock_comment: Mock,
    create_action: Mock,
) -> None:
    moderator = Mock()
    comment = Mock(id=1, author_id=2)
    filter_comments = select_comments_for_update.return_value.filter
    filter_comments.return_value.first.return_value = comment
    lock_comment.return_value = comment

    result = CommunityModerationService.moderate_comment.__wrapped__(
        moderator=moderator,
        comment_id=comment.id,
        action_type=ModerationAction.ActionType.LOCK,
    )

    assert result is comment
    select_comments_for_update.assert_called_once_with()
    filter_comments.assert_called_once_with(id=comment.id)
    lock_comment.assert_called_once_with(comment=comment)
    create_action.assert_called_once_with(
        moderator=moderator,
        target_user_id=comment.author_id,
        comment=comment,
        action_type=ModerationAction.ActionType.LOCK,
        reason="",
    )


@patch(
    "apps.community.services.moderation_service.CommunityComment.objects.select_for_update"
)
@patch(
    "apps.community.services.moderation_service.CommunityPost.objects.select_for_update"
)
def test_moderate_missing_targets_raise_application_errors(
    select_posts_for_update: Mock,
    select_comments_for_update: Mock,
) -> None:
    moderator = Mock()
    select_posts_for_update.return_value.filter.return_value.first.return_value = None
    select_comments_for_update.return_value.filter.return_value.first.return_value = (
        None
    )

    with pytest.raises(CommunityPostNotFound):
        CommunityModerationService.moderate_post.__wrapped__(
            moderator=moderator,
            post_id=999,
            action_type=ModerationAction.ActionType.HIDE,
        )

    with pytest.raises(CommunityCommentNotFound):
        CommunityModerationService.moderate_comment.__wrapped__(
            moderator=moderator,
            comment_id=999,
            action_type=ModerationAction.ActionType.LOCK,
        )
