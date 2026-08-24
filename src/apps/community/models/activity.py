from django.db import models
from django.db.models import Q

from .choices import FeedPolicy, Visibility


class Activity(models.Model):
    class ActivityType(models.TextChoices):
        POST_CREATED = "post_created", "Post created"
        USER_SUBJECT_CREATED = "user_subject_created", "User subject created"
        USER_SUBJECT_UPDATED = "user_subject_updated", "User subject updated"
        REVIEW_CREATED = "review_created", "Review created"
        COLLECTION_CREATED = "collection_created", "Collection created"
        COLLECTION_ITEM_ADDED = "collection_item_added", "Collection item added"
        COMMENT_CREATED = "comment_created", "Comment created"
        USER_FOLLOWED = "user_followed", "User followed"

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="activities",
    )
    target_user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="targeted_activities",
    )
    entity = models.ForeignKey(
        "index.Entity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activities",
    )
    user_subject = models.ForeignKey(
        "users.UserSubject",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    review = models.ForeignKey(
        "users.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    collection = models.ForeignKey(
        "users.Collection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    collection_item = models.ForeignKey(
        "users.CollectionItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    post = models.ForeignKey(
        "community.CommunityPost",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    comment = models.ForeignKey(
        "community.CommunityComment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
    )
    activity_type = models.CharField(max_length=64, choices=ActivityType.choices)
    message = models.CharField(max_length=1024, blank=True)
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    feed_policy = models.CharField(
        max_length=16,
        choices=FeedPolicy.choices,
        default=FeedPolicy.NORMAL,
    )
    group_key = models.CharField(max_length=256, blank=True)
    dedupe_key = models.CharField(max_length=256, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_activity"
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=~Q(dedupe_key=""),
                name="uq_c_activity_dedupe_key",
            )
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_ca_user_created"),
            models.Index(
                fields=["activity_type", "-created_at"], name="idx_ca_type_created"
            ),
            models.Index(
                fields=["visibility", "feed_policy", "-created_at"], name="idx_ca_feed"
            ),
            models.Index(
                fields=["group_key", "-created_at"], name="idx_ca_group_created"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.activity_type}"


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        FOLLOWED = "followed", "Followed"
        COMMENTED = "commented", "Commented"
        REACTED = "reacted", "Reacted"
        MENTIONED = "mentioned", "Mentioned"

    recipient = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="notifications"
    )
    actor = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sent_notifications",
    )
    notification_type = models.CharField(
        max_length=32, choices=NotificationType.choices
    )
    activity = models.ForeignKey(
        "community.Activity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    post = models.ForeignKey(
        "community.CommunityPost",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    comment = models.ForeignKey(
        "community.CommunityComment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    review = models.ForeignKey(
        "users.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    collection = models.ForeignKey(
        "users.Collection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    metadata = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_notification"
        indexes = [
            models.Index(
                fields=["recipient", "read_at", "-created_at"],
                name="idx_cn_recipient_read",
            ),
            models.Index(
                fields=["recipient", "-created_at"],
                name="idx_cn_recipient_created",
            ),
        ]
