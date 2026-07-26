from django.db import models
from django.db.models import Q


class CommunityReport(models.Model):
    class ReportReason(models.TextChoices):
        SPAM = "spam", "Spam"
        HARASSMENT = "harassment", "Harassment"
        SPOILER = "spoiler", "Spoiler"
        ILLEGAL = "illegal", "Illegal"
        OTHER = "other", "Other"

    class ReportStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    reporter = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="community_reports"
    )
    reported_user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reported_community_items",
    )
    post = models.ForeignKey(
        "community.CommunityPost",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reports",
    )
    comment = models.ForeignKey(
        "community.CommunityComment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reports",
    )
    review = models.ForeignKey(
        "users.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_reports",
    )
    collection = models.ForeignKey(
        "users.Collection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_reports",
    )
    activity = models.ForeignKey(
        "community.Activity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reports",
    )
    reason = models.CharField(max_length=32, choices=ReportReason.choices)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
    )
    resolved_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_community_reports",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_report"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        post__isnull=False,
                        comment__isnull=True,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=False,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=True,
                        review__isnull=False,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=True,
                        review__isnull=True,
                        collection__isnull=False,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        comment__isnull=True,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=False,
                    )
                ),
                name="ck_c_report_single_target",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "-created_at"],
                name="idx_creport_status_created",
            ),
            models.Index(
                fields=["reporter", "-created_at"],
                name="idx_creport_reporter_created",
            ),
        ]


class ModerationAction(models.Model):
    class ActionType(models.TextChoices):
        HIDE = "hide", "Hide"
        LOCK = "lock", "Lock"
        DELETE = "delete", "Delete"
        WARN = "warn", "Warn"
        MUTE = "mute", "Mute"
        BAN = "ban", "Ban"

    moderator = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="moderation_actions"
    )
    target_user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_moderation_actions",
    )
    report = models.ForeignKey(
        "community.CommunityReport",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    post = models.ForeignKey(
        "community.CommunityPost",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    comment = models.ForeignKey(
        "community.CommunityComment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    activity = models.ForeignKey(
        "community.Activity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    review = models.ForeignKey(
        "users.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    collection = models.ForeignKey(
        "users.Collection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="moderation_actions",
    )
    action_type = models.CharField(max_length=16, choices=ActionType.choices)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_moderation_action"
        indexes = [
            models.Index(fields=["moderator", "-created_at"], name="idx_cma_moderator"),
            models.Index(fields=["target_user", "-created_at"], name="idx_cma_target"),
            models.Index(fields=["action_type", "-created_at"], name="idx_cma_type"),
        ]
