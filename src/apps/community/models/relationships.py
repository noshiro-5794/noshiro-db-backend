from django.db import models
from django.db.models import Q


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
            models.UniqueConstraint(
                fields=["follower", "following"], name="uq_c_follow"
            ),
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

    def __str__(self) -> str:
        return f"follower={self.follower_id} following={self.following_id}"


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
            models.UniqueConstraint(
                fields=["user", "blocked_user"], name="uq_c_user_block"
            ),
            models.CheckConstraint(
                condition=~Q(user=models.F("blocked_user")),
                name="ck_c_no_self_block",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_cub_user_created"),
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
            models.UniqueConstraint(
                fields=["user", "muted_user"], name="uq_c_user_mute"
            ),
            models.CheckConstraint(
                condition=~Q(user=models.F("muted_user")),
                name="ck_c_no_self_mute",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_cum_user_created"),
        ]
