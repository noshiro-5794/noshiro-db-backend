from django.db import models
from django.db.models import Q


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
            models.Index(
                fields=["reaction_type", "-created_at"], name="idx_cr_type_created"
            ),
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
                    | Q(
                        post__isnull=True, review__isnull=False, collection__isnull=True
                    )
                    | Q(
                        post__isnull=True, review__isnull=True, collection__isnull=False
                    )
                ),
                name="ck_c_bookmark_single_target",
            ),
            models.UniqueConstraint(fields=["user", "post"], name="uq_c_bookmark_post"),
            models.UniqueConstraint(
                fields=["user", "review"], name="uq_c_bookmark_review"
            ),
            models.UniqueConstraint(
                fields=["user", "collection"], name="uq_c_bookmark_collection"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_cb_user_created"),
        ]
