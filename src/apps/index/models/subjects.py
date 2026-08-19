import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models

from .base import LegacySourceModel, TimestampedModel


class Episode(LegacySourceModel):
    entity = models.OneToOneField(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="episode_projection",
    )
    title = models.CharField(max_length=256, blank=True)
    type = models.CharField(max_length=64, blank=True)
    ep_num = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    sort = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    title_cn = models.CharField(max_length=256, blank=True)
    disc = models.PositiveSmallIntegerField(blank=True, null=True)
    comment_count = models.PositiveIntegerField(blank=True, null=True)
    raw_duration = models.CharField(max_length=64, blank=True)
    duration = models.DurationField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    description = models.TextField(blank=True)
    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="episodes"
    )

    class Meta:
        db_table = "episode"
        constraints = [
            models.UniqueConstraint(
                fields=["info_source", "id_source"],
                name="uq_episode_info_id_source",
            )
        ]

    def __str__(self) -> str:
        return self.title


class Subject(LegacySourceModel):
    class SubjectType(models.TextChoices):
        ANIME = "anime", "Anime"
        GALGAME = "galgame", "Galgame"
        GAME = "game", "Game"
        MANGA = "manga", "Manga"
        NOVEL = "novel", "Novel"
        BOOK = "book", "Book"
        MUSIC = "music", "Music"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject_type = models.CharField(
        max_length=64, choices=SubjectType.choices, blank=True
    )
    title = models.CharField(max_length=256, blank=True)
    title_cn = models.CharField(max_length=256, blank=True)
    date = models.DateField(blank=True, null=True)
    image_original = models.URLField(max_length=1024, blank=True)
    image_thumbnail = models.URLField(max_length=1024, blank=True)
    platform = models.CharField(max_length=256, blank=True)
    description = models.TextField(blank=True)
    nsfw = models.BooleanField(default=False)
    series = models.BooleanField(default=False)
    volumes = models.IntegerField(blank=True, null=True)
    eps = models.IntegerField(blank=True, null=True)
    total_episodes = models.IntegerField(blank=True, null=True)
    infobox = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    staff = models.ManyToManyField(
        "Staff", through="SubjectStaffRelation", related_name="subjects", blank=True
    )
    characters = models.ManyToManyField(
        "Character",
        through="SubjectCharacterRelation",
        related_name="subjects",
        blank=True,
    )

    class Meta:
        db_table = "subject"
        constraints = [
            models.UniqueConstraint(
                fields=["info_source", "id_source"],
                name="uq_subject_info_id_source",
            )
        ]
        indexes = [
            models.Index(fields=["id_source"], name="idx_subject_id_source"),
            GinIndex(
                name="idx_subject_title", fields=["title"], opclasses=["gin_trgm_ops"]
            ),
            GinIndex(
                name="idx_subject_title_cn",
                fields=["title_cn"],
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.subject_type}] {self.title or 'Untitled'} ({self.date or 'Unknown'})"


class CalendarSubject(models.Model):
    subject = models.OneToOneField(
        "Subject", on_delete=models.CASCADE, related_name="calendar_entry"
    )
    weekday_en = models.CharField(max_length=16, blank=True)
    collection_doing = models.PositiveIntegerField(default=0)
    image_url = models.URLField(max_length=1024, blank=True)

    class Meta:
        db_table = "calendar_subject"
        indexes = [
            models.Index(
                fields=["weekday_en", "-collection_doing"],
                name="idx_cal_weekday_doing",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.weekday_en}: {self.subject}"


class SubjectStaffRelation(models.Model):
    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="staff_relations"
    )
    staff = models.ForeignKey(
        "Staff", on_delete=models.CASCADE, related_name="subject_relations"
    )
    role = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "subject_staff_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "staff", "role"], name="uq_subject_staff_role"
            )
        ]
        indexes = [
            models.Index(fields=["subject", "role"], name="idx_subj_stf_sr"),
        ]

    def __str__(self) -> str:
        return f"{self.subject} - {self.staff} ({self.role})"


class SubjectCharacterRelation(models.Model):
    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="character_relations"
    )
    character = models.ForeignKey(
        "Character", on_delete=models.CASCADE, related_name="subject_relations"
    )
    role = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "subject_character_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "character", "role"],
                name="uq_subject_character_role",
            )
        ]
        indexes = [
            models.Index(fields=["subject", "role"], name="idx_subj_char_sr"),
        ]

    def __str__(self) -> str:
        return f"{self.subject} - {self.character} ({self.role})"


class SubjectCharacterActorRelation(models.Model):
    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="character_actor_relations"
    )
    character = models.ForeignKey(
        "Character", on_delete=models.CASCADE, related_name="actor_relations"
    )
    actor = models.ForeignKey(
        "Staff", on_delete=models.CASCADE, related_name="voice_roles"
    )

    class Meta:
        db_table = "subject_character_actor_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "character", "actor"],
                name="uq_subject_character_actor",
            )
        ]
        indexes = [
            models.Index(fields=["character", "actor"], name="idx_subj_char_act_ca"),
        ]

    def __str__(self) -> str:
        return f"{self.subject} - {self.character} ({self.actor})"


class SubjectSubjectRelation(models.Model):
    source = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="outgoing_relations"
    )
    target = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="incoming_relations"
    )
    relation = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "subject_subject_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "target", "relation"],
                name="uq_subject_subject_relation",
            )
        ]
        indexes = [
            models.Index(fields=["source", "relation"], name="idx_subj_subj_sr"),
        ]

    def __str__(self) -> str:
        return f"{self.source} -> {self.target} ({self.relation})"


class RelationEvidence(TimestampedModel):
    source = models.ForeignKey(
        "Provider",
        on_delete=models.PROTECT,
        related_name="relation_evidence",
    )
    subject_relation = models.ForeignKey(
        "SubjectSubjectRelation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evidence",
    )
    staff_relation = models.ForeignKey(
        "SubjectStaffRelation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evidence",
    )
    character_relation = models.ForeignKey(
        "SubjectCharacterRelation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evidence",
    )
    character_actor_relation = models.ForeignKey(
        "SubjectCharacterActorRelation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evidence",
    )

    class Meta:
        db_table = "relation_evidence"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        subject_relation__isnull=False,
                        staff_relation__isnull=True,
                        character_relation__isnull=True,
                        character_actor_relation__isnull=True,
                    )
                    | models.Q(
                        subject_relation__isnull=True,
                        staff_relation__isnull=False,
                        character_relation__isnull=True,
                        character_actor_relation__isnull=True,
                    )
                    | models.Q(
                        subject_relation__isnull=True,
                        staff_relation__isnull=True,
                        character_relation__isnull=False,
                        character_actor_relation__isnull=True,
                    )
                    | models.Q(
                        subject_relation__isnull=True,
                        staff_relation__isnull=True,
                        character_relation__isnull=True,
                        character_actor_relation__isnull=False,
                    )
                ),
                name="ck_relation_evidence_single_target",
            ),
            models.UniqueConstraint(
                fields=["source", "subject_relation"],
                name="uq_relation_evidence_subject",
            ),
            models.UniqueConstraint(
                fields=["source", "staff_relation"],
                name="uq_relation_evidence_staff",
            ),
            models.UniqueConstraint(
                fields=["source", "character_relation"],
                name="uq_relation_evidence_character",
            ),
            models.UniqueConstraint(
                fields=["source", "character_actor_relation"],
                name="uq_relation_evidence_actor",
            ),
        ]

    def __str__(self) -> str:
        relation_id = (
            self.subject_relation_id
            or self.staff_relation_id
            or self.character_relation_id
            or self.character_actor_relation_id
        )
        return f"{self.source.slug}:{relation_id}"
