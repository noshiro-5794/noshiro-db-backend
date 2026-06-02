from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser, BaseUserManager


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):

    username = None
    email = models.EmailField(unique=True)
    is_email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "user"
        indexes = [
            models.Index(fields=["email"], name="idx_user_email"),
        ]

    def __str__(self):
        return self.email


class UserProfile(models.Model):

    class Language(models.TextChoices):
        AUTO = "auto", "Auto"
        EN_US = "en-US", "English"
        ZH_CN = "zh-CN", "Chinese"
        JA_JP = "ja-JP", "Japanese"

    class Appearance(models.TextChoices):
        AUTO = "auto", "Auto"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="profile"
    )
    nickname = models.CharField(max_length=256, unique=True)
    avatar = models.URLField(max_length=1024, blank=True)
    bio = models.TextField(blank=True)
    language = models.CharField(
        max_length=16,
        choices=Language.choices,
        default=Language.AUTO,
    )
    appearance = models.CharField(
        max_length=16,
        choices=Appearance.choices,
        default=Appearance.AUTO,
    )
    theme_color = models.CharField(max_length=16, default="#7F6FB0")

    class Meta:
        db_table = "user_profile"
        indexes = [
            models.Index(fields=["nickname"], name="idx_user_nickname"),
        ]

    def __str__(self):
        return self.nickname


class EmailVerification(models.Model):

    class Purpose(models.TextChoices):
        REGISTER = "register", "Register"
        LOGIN = "login", "Login"
        RESET_PASSWORD = "reset_password", "Reset Password"

    email = models.EmailField()
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    expire_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_verification"
        indexes = [
            models.Index(fields=["email", "purpose"], name="idx_ev_email_purpose"),
            models.Index(fields=["expire_at"], name="idx_ev_expire_at"),
        ]


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
    watch_start_date = models.CharField(max_length=16, blank=True)
    watch_end_date = models.CharField(max_length=16, blank=True)
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
            models.Index(fields=["subject"], name="idx_subject"),
            models.Index(
                fields=["subject", "-simple_rating"], name="idx_subject_simple_rating"
            ),
            models.Index(fields=["status"], name="idx_status"),
        ]

    def __str__(self):
        return f"{self.user.profile.nickname} - {self.subject.title} ({self.status})"


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

    def __str__(self):
        return f"{self.user_subject} - {self.key}: {self.value}"


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
            models.Index(fields=["user"], name="idx_user_tag_user"),
            models.Index(fields=["name"], name="idx_user_tag_name"),
        ]

    def __str__(self):
        return f"{self.user.profile.nickname} - {self.name}"


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

    def __str__(self):
        return f"{self.user_subject} - {self.tag.name}"


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

    def __str__(self):
        return f"{self.user_subject} - {self.episode.title}"


class Review(models.Model):

    user_subject = models.ForeignKey(
        "UserSubject", on_delete=models.CASCADE, related_name="reviews"
    )
    title = models.CharField(max_length=256)
    content = models.TextField()
    is_public = models.BooleanField(default=True)
    is_spoiler = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "review"
        indexes = [
            models.Index(fields=["-created_at"], name="idx_review_created"),
            models.Index(fields=["-updated_at"], name="idx_review_updated"),
        ]

    def __str__(self):
        return f"{self.title} ({self.user_subject_id})"


class Collection(models.Model):

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="collections"
    )
    name = models.CharField(max_length=256)
    simple_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)

    class Meta:
        db_table = "collection"
        constraints = [
            models.CheckConstraint(
                condition=Q(simple_rating__isnull=True)
                | (Q(simple_rating__gte=1) & Q(simple_rating__lte=5)),
                name="ck_collection_simple_rating",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="idx_collection_user"),
            models.Index(fields=["user", "is_public"], name="idx_collection_public"),
        ]

    def __str__(self):
        return f"{self.user.profile.nickname} - {self.name}"


class CollectionItem(models.Model):

    collection = models.ForeignKey(
        "Collection", on_delete=models.CASCADE, related_name="items"
    )
    user_subject = models.ForeignKey(
        "UserSubject", on_delete=models.CASCADE, related_name="collection_items"
    )
    order = models.IntegerField(default=0)
    relation = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "collection_item"
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "user_subject"], name="uq_collection_user_subject"
            )
        ]
        indexes = [
            models.Index(fields=["collection"], name="idx_ci_collection"),
            models.Index(fields=["user_subject"], name="idx_ci_user_subject"),
        ]

    def __str__(self):
        return (
            f"{self.collection} - {self.user_subject.subject.title} ({self.relation})"
        )

