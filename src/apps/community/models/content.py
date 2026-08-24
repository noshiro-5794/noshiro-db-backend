from django.db import models
from django.db.models import Q

from .choices import FeedPolicy, Visibility


class CommunityPost(models.Model):
    class PostType(models.TextChoices):
        STATUS = "status", "Status"
        ENTITY = "entity", "Entity"

    author = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="community_posts"
    )
    entity = models.ForeignKey(
        "index.Entity",
        on_delete=models.PROTECT,
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
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(post_type="entity", entity__isnull=False)
                    | Q(
                        post_type="status",
                        entity__isnull=True,
                    )
                ),
                name="ck_c_post_type_target",
            )
        ]
        indexes = [
            models.Index(
                fields=["author", "-created_at"], name="idx_cp_author_created"
            ),
            models.Index(
                fields=["entity", "-last_activity_at"], name="idx_cp_entity_active"
            ),
            models.Index(
                fields=["visibility", "feed_policy", "-created_at"], name="idx_cp_feed"
            ),
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
                    Q(
                        post__isnull=False,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        review__isnull=False,
                        collection__isnull=True,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        review__isnull=True,
                        collection__isnull=False,
                        activity__isnull=True,
                    )
                    | Q(
                        post__isnull=True,
                        review__isnull=True,
                        collection__isnull=True,
                        activity__isnull=False,
                    )
                ),
                name="ck_c_comment_single_target",
            )
        ]
        indexes = [
            models.Index(
                fields=["author", "-created_at"], name="idx_cc_author_created"
            ),
            models.Index(fields=["post", "-created_at"], name="idx_cc_post_created"),
            models.Index(
                fields=["review", "-created_at"], name="idx_cc_review_created"
            ),
            models.Index(
                fields=["collection", "-created_at"], name="idx_cc_collection_created"
            ),
            models.Index(
                fields=["activity", "-created_at"], name="idx_cc_activity_created"
            ),
            models.Index(
                fields=["parent", "-created_at"], name="idx_cc_parent_created"
            ),
        ]
