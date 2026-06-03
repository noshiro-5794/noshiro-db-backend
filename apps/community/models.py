from django.db import models
from django.db.models import Q


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    FOLLOWERS = "followers", "Followers"
    PRIVATE = "private", "Private"


class FeedPolicy(models.TextChoices):
    HIDDEN = "hidden", "Hidden"
    NORMAL = "normal", "Normal"
    FEATURED = "featured", "Featured"


class UserFollow(models.Model):

    follower = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="following_relations"
    )
    following = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="follower_relations"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_user_follow"
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="uq_c_follow"),
            models.CheckConstraint(
                condition=~Q(follower=models.F("following")),
                name="ck_c_no_self_follow",
            ),
        ]
        indexes = [
            models.Index(
                fields=["follower", "-created_at"], name="idx_cuf_follower_created"
            ),
            models.Index(
                fields=["following", "-created_at"], name="idx_cuf_following_created"
            ),
        ]

    def __str__(self):
        return f"{self.follower} - {self.following}"


class UserBlock(models.Model):

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="blocking_relations"
    )
    blocked_user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="blocked_by_relations"
    )
    reason = models.CharField(max_length=256, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_user_block"
        constraints = [
            models.UniqueConstraint(fields=["user", "blocked_user"], name="uq_c_user_block"),
            models.CheckConstraint(
                condition=~Q(user=models.F("blocked_user")),
                name="ck_c_no_self_block",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_cub_user_created"),
            models.Index(fields=["blocked_user"], name="idx_cub_blocked_user"),
        ]


class UserMute(models.Model):

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="muting_relations"
    )
    muted_user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="muted_by_relations"
    )
    reason = models.CharField(max_length=256, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_user_mute"
        constraints = [
            models.UniqueConstraint(fields=["user", "muted_user"], name="uq_c_user_mute"),
            models.CheckConstraint(
                condition=~Q(user=models.F("muted_user")),
                name="ck_c_no_self_mute",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_cum_user_created"),
            models.Index(fields=["muted_user"], name="idx_cum_muted_user"),
        ]


class CommunityPost(models.Model):

    class PostType(models.TextChoices):
        STATUS = "status", "Status"
        SUBJECT = "subject", "Subject"

    author = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="community_posts"
    )
    subject = models.ForeignKey(
        "index.Subject",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_posts",
    )
    post_type = models.CharField(
        max_length=16,
        choices=PostType.choices,
        default=PostType.STATUS,
    )
    content = models.TextField()
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
    is_spoiler = models.BooleanField(default=False)
    is_nsfw = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    reply_count = models.PositiveIntegerField(default=0)
    reaction_count = models.PositiveIntegerField(default=0)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "community_post"
        indexes = [
            models.Index(fields=["author", "-created_at"], name="idx_cp_author_created"),
            models.Index(fields=["subject", "-last_activity_at"], name="idx_cp_subject_active"),
            models.Index(fields=["visibility", "feed_policy", "-created_at"], name="idx_cp_feed"),
        ]


class CommunityComment(models.Model):

    author = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="community_comments"
    )
    post = models.ForeignKey(
        "community.CommunityPost",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comments",
    )
    review = models.ForeignKey(
        "users.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_comments",
    )
    collection = models.ForeignKey(
        "users.Collection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_comments",
    )
    activity = models.ForeignKey(
        "community.Activity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comments",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    content = models.TextField()
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    is_spoiler = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    reply_count = models.PositiveIntegerField(default=0)
    reaction_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "community_comment"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(post__isnull=False, review__isnull=True, collection__isnull=True, activity__isnull=True)
                    | Q(post__isnull=True, review__isnull=False, collection__isnull=True, activity__isnull=True)
                    | Q(post__isnull=True, review__isnull=True, collection__isnull=False, activity__isnull=True)
                    | Q(post__isnull=True, review__isnull=True, collection__isnull=True, activity__isnull=False)
                ),
                name="ck_c_comment_single_target",
            )
        ]
        indexes = [
            models.Index(fields=["author", "-created_at"], name="idx_cc_author_created"),
            models.Index(fields=["post", "-created_at"], name="idx_cc_post_created"),
            models.Index(fields=["review", "-created_at"], name="idx_cc_review_created"),
            models.Index(fields=["collection", "-created_at"], name="idx_cc_collection_created"),
            models.Index(fields=["activity", "-created_at"], name="idx_cc_activity_created"),
            models.Index(fields=["parent", "-created_at"], name="idx_cc_parent_created"),
        ]


class CommunityReaction(models.Model):

    class ReactionType(models.TextChoices):
        LIKE = "like", "Like"
        USEFUL = "useful", "Useful"
        AGREE = "agree", "Agree"

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="community_reactions"
    )
    post = models.ForeignKey(
        "community.CommunityPost",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reactions",
    )
    comment = models.ForeignKey(
        "community.CommunityComment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reactions",
    )
    review = models.ForeignKey(
        "users.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_reactions",
    )
    collection = models.ForeignKey(
        "users.Collection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_reactions",
    )
    activity = models.ForeignKey(
        "community.Activity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reactions",
    )
    reaction_type = models.CharField(
        max_length=16,
        choices=ReactionType.choices,
        default=ReactionType.LIKE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_reaction"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(post__isnull=False, comment__isnull=True, review__isnull=True, collection__isnull=True, activity__isnull=True)
                    | Q(post__isnull=True, comment__isnull=False, review__isnull=True, collection__isnull=True, activity__isnull=True)
                    | Q(post__isnull=True, comment__isnull=True, review__isnull=False, collection__isnull=True, activity__isnull=True)
                    | Q(post__isnull=True, comment__isnull=True, review__isnull=True, collection__isnull=False, activity__isnull=True)
                    | Q(post__isnull=True, comment__isnull=True, review__isnull=True, collection__isnull=True, activity__isnull=False)
                ),
                name="ck_c_reaction_single_target",
            ),
            models.UniqueConstraint(
                fields=["user", "post", "reaction_type"],
                name="uq_c_reaction_post",
            ),
            models.UniqueConstraint(
                fields=["user", "comment", "reaction_type"],
                name="uq_c_reaction_comment",
            ),
            models.UniqueConstraint(
                fields=["user", "review", "reaction_type"],
                name="uq_c_reaction_review",
            ),
            models.UniqueConstraint(
                fields=["user", "collection", "reaction_type"],
                name="uq_c_reaction_collection",
            ),
            models.UniqueConstraint(
                fields=["user", "activity", "reaction_type"],
                name="uq_c_reaction_activity",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_cr_user_created"),
            models.Index(fields=["reaction_type", "-created_at"], name="idx_cr_type_created"),
        ]


class CommunityBookmark(models.Model):

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="community_bookmarks"
    )
    post = models.ForeignKey(
        "community.CommunityPost",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="bookmarks",
    )
    review = models.ForeignKey(
        "users.Review",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_bookmarks",
    )
    collection = models.ForeignKey(
        "users.Collection",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="community_bookmarks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "community_bookmark"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(post__isnull=False, review__isnull=True, collection__isnull=True)
                    | Q(post__isnull=True, review__isnull=False, collection__isnull=True)
                    | Q(post__isnull=True, review__isnull=True, collection__isnull=False)
                ),
                name="ck_c_bookmark_single_target",
            ),
            models.UniqueConstraint(fields=["user", "post"], name="uq_c_bookmark_post"),
            models.UniqueConstraint(fields=["user", "review"], name="uq_c_bookmark_review"),
            models.UniqueConstraint(fields=["user", "collection"], name="uq_c_bookmark_collection"),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_cb_user_created"),
        ]


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
    subject = models.ForeignKey(
        "index.Subject",
        on_delete=models.CASCADE,
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
            models.Index(fields=["activity_type", "-created_at"], name="idx_ca_type_created"),
            models.Index(fields=["visibility", "feed_policy", "-created_at"], name="idx_ca_feed"),
            models.Index(fields=["group_key", "-created_at"], name="idx_ca_group_created"),
        ]

    def __str__(self):
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
    notification_type = models.CharField(max_length=32, choices=NotificationType.choices)
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
            models.Index(fields=["recipient", "read_at", "-created_at"], name="idx_cn_recipient_read"),
            models.Index(fields=["recipient", "-created_at"], name="idx_cn_recipient_created"),
        ]


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
        indexes = [
            models.Index(fields=["status", "-created_at"], name="idx_creport_status_created"),
            models.Index(fields=["reporter", "-created_at"], name="idx_creport_reporter_created"),
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
