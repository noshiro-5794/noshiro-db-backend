from django.db import models
from django.db.models import Q


class UserSubject(models.Model):
    class Status(models.TextChoices):
        DOING = "doing", "Doing"
        WISH = "wish", "Wish"
        DONE = "done", "Done"
        ON_HOLD = "on_hold", "On Hold"
        DROP = "drop", "Drop"

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="subjects"
    )
    subject = models.ForeignKey(
        "index.Subject", on_delete=models.CASCADE, related_name="users"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    simple_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    comment = models.TextField(blank=True)
    watch_start_date = models.DateField(null=True, blank=True)
    watch_end_date = models.DateField(null=True, blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_subject"
        constraints = [
            models.UniqueConstraint(fields=["user", "subject"], name="uq_user_subject"),
            models.CheckConstraint(
                condition=Q(simple_rating__isnull=True)
                | (Q(simple_rating__gte=1) & Q(simple_rating__lte=5)),
                name="ck_simple_rating",
            ),
            models.CheckConstraint(
                condition=Q(rating__isnull=True)
                | (Q(rating__gte=0) & Q(rating__lte=10)),
                name="ck_rating",
            ),
            models.CheckConstraint(
                condition=Q(watch_start_date__isnull=True)
                | Q(watch_end_date__isnull=True)
                | Q(watch_start_date__lte=models.F("watch_end_date")),
                name="ck_watch_date_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "status", "-updated_at"], name="idx_user_status_updated"
            ),
            models.Index(fields=["user", "-updated_at"], name="idx_user_updated"),
            models.Index(
                fields=["user", "-simple_rating"], name="idx_user_simple_rating"
            ),
            models.Index(fields=["user", "-rating"], name="idx_user_rating"),
            models.Index(
                fields=["user", "watch_end_date"], name="idx_user_watch_end_date"
            ),
            models.Index(
                fields=["subject", "-simple_rating"], name="idx_subject_simple_rating"
            ),
            models.Index(fields=["status"], name="idx_status"),
        ]

    def __str__(self) -> str:
        return f"user={self.user_id} subject={self.subject_id} status={self.status}"


class UserSubjectRatingDetail(models.Model):
    user_subject = models.ForeignKey(
        "UserSubject", on_delete=models.CASCADE, related_name="rating_details"
    )
    key = models.CharField(max_length=256)
    value = models.DecimalField(max_digits=3, decimal_places=1)

    class Meta:
        db_table = "user_subject_rating_detail"
        constraints = [
            models.UniqueConstraint(
                fields=["user_subject", "key"], name="uq_user_subject_key"
            ),
            models.CheckConstraint(
                condition=Q(value__gte=0) & Q(value__lte=10),
                name="ck_rating_value",
            ),
        ]

    def __str__(self) -> str:
        return f"user_subject={self.user_subject_id} {self.key}={self.value}"


class UserTag(models.Model):
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="tags"
    )
    name = models.CharField(max_length=64)

    class Meta:
        db_table = "user_tag"
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="uq_user_tag"),
        ]
        indexes = [
            models.Index(fields=["name"], name="idx_user_tag_name"),
        ]

    def __str__(self) -> str:
        return f"user={self.user_id} tag={self.name}"


class UserSubjectTag(models.Model):
    user_subject = models.ForeignKey(
        "UserSubject", on_delete=models.CASCADE, related_name="tag_relations"
    )
    tag = models.ForeignKey(
        "UserTag", on_delete=models.CASCADE, related_name="subject_relations"
    )

    class Meta:
        db_table = "user_subject_tag"
        constraints = [
            models.UniqueConstraint(
                fields=["user_subject", "tag"], name="uq_user_subject_tag"
            )
        ]

    def __str__(self) -> str:
        return f"user_subject={self.user_subject_id} tag={self.tag_id}"


class UserEpisodeProgress(models.Model):
    user_subject = models.ForeignKey(
        "UserSubject", on_delete=models.CASCADE, related_name="episode_progress"
    )
    episode = models.ForeignKey(
        "index.Episode", on_delete=models.CASCADE, related_name="users_progress"
    )
    is_finished = models.BooleanField(default=False)

    class Meta:
        db_table = "user_episode_progress"
        constraints = [
            models.UniqueConstraint(
                fields=["user_subject", "episode"], name="uq_user_subject_episode"
            )
        ]

    def __str__(self) -> str:
        return f"user_subject={self.user_subject_id} episode={self.episode_id}"
