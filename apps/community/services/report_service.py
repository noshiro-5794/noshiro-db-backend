from django.db import transaction
from django.utils import timezone

from apps.community.models import (
    Activity,
    CommunityComment,
    CommunityPost,
    CommunityReport,
    ModerationAction,
)
from apps.community.selectors.target_selector import CommunityTargetSelector
from apps.community.services.comment_service import CommunityCommentService
from apps.community.services.post_service import CommunityPostService
from apps.users.models import Collection, Review


class CommunityReportService:

    @staticmethod
    def _target_kwargs(*, target_type: str, target):
        return {target_type: target}

    @staticmethod
    def _reported_user_for_target(target):
        if isinstance(target, CommunityPost):
            return target.author
        if isinstance(target, CommunityComment):
            return target.author
        if isinstance(target, Review):
            return target.user_subject.user
        if isinstance(target, Collection):
            return target.user
        if isinstance(target, Activity):
            return target.user
        return None

    @staticmethod
    @transaction.atomic
    def create_report(
        *,
        reporter,
        target_type: str,
        target_id: int,
        reason: str,
        description="",
    ):
        target = CommunityTargetSelector.get_target_or_raise(
            target_type=target_type,
            target_id=target_id,
            allowed_targets=CommunityTargetSelector.REPORT_TARGETS,
        )

        return CommunityReport.objects.create(
            reporter=reporter,
            reported_user=CommunityReportService._reported_user_for_target(target),
            reason=reason,
            description=description,
            **CommunityReportService._target_kwargs(
                target_type=target_type,
                target=target,
            ),
        )

    @staticmethod
    @transaction.atomic
    def resolve_report(
        *,
        report,
        moderator,
        status: str,
        action_type=None,
        moderation_reason="",
    ):
        report.status = status
        report.resolved_by = moderator
        report.resolved_at = timezone.now()
        report.save(update_fields=["status", "resolved_by", "resolved_at"])

        if action_type:
            if action_type == ModerationAction.ActionType.HIDE:
                if report.post:
                    CommunityPostService.hide_post(post=report.post)
                elif report.comment:
                    CommunityCommentService.hide_comment(comment=report.comment)
                elif report.activity:
                    report.activity.feed_policy = "hidden"
                    report.activity.save(update_fields=["feed_policy"])
            elif action_type == ModerationAction.ActionType.LOCK:
                if report.post:
                    CommunityPostService.lock_post(post=report.post)
                elif report.comment:
                    CommunityCommentService.lock_comment(comment=report.comment)

            ModerationAction.objects.create(
                moderator=moderator,
                target_user=report.reported_user,
                report=report,
                post=report.post,
                comment=report.comment,
                activity=report.activity,
                review=report.review,
                collection=report.collection,
                action_type=action_type,
                reason=moderation_reason,
                metadata={"report_status": status},
            )

        return report
