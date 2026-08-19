import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from .base import ContentSafety, TimestampedModel


class Entity(TimestampedModel):
    class Kind(models.TextChoices):
        WORK = "work", "Work"
        RELEASE = "release", "Release"
        EPISODE = "episode", "Episode"
        CONTRIBUTOR = "contributor", "Contributor"
        CHARACTER = "character", "Character"
        UNCLASSIFIED = "unclassified", "Unclassified"

    class Lifecycle(models.TextChoices):
        ACTIVE = "active", "Active"
        MERGED = "merged", "Merged"
        RETIRED = "retired", "Retired"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        AUTHENTICATED = "authenticated", "Authenticated"
        RESTRICTED = "restricted", "Restricted"

    class Audience(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        GENERAL = "general", "General"
        ADULT = "adult", "Adult"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    lifecycle = models.CharField(
        max_length=16,
        choices=Lifecycle.choices,
        default=Lifecycle.ACTIVE,
    )
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    audience = models.CharField(
        max_length=16,
        choices=Audience.choices,
        default=Audience.UNKNOWN,
    )
    spoiler_level = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "index_entity"
        constraints = [
            models.CheckConstraint(
                condition=Q(spoiler_level__lte=3),
                name="ck_entity_spoiler_level",
            )
        ]
        indexes = [
            models.Index(
                fields=["kind", "lifecycle"], name="idx_entity_kind_lifecycle"
            ),
            models.Index(
                fields=["visibility", "audience"],
                name="idx_entity_visibility_rating",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"


class Work(TimestampedModel):
    class WorkType(models.TextChoices):
        ANIME = "anime", "Anime"
        GALGAME = "galgame", "Galgame"
        MANGA = "manga", "Manga"
        NOVEL = "novel", "Novel"
        GAME = "game", "Game"
        MUSIC = "music", "Music"
        OTHER = "other", "Other"
        UNCLASSIFIED = "unclassified", "Unclassified"

    entity = models.OneToOneField(
        "Entity",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="work",
    )
    work_type = models.CharField(
        max_length=32,
        choices=WorkType.choices,
        default=WorkType.UNCLASSIFIED,
    )

    class Meta:
        db_table = "work"
        indexes = [models.Index(fields=["work_type"], name="idx_work_type")]


class AnimeProfile(TimestampedModel):
    work = models.OneToOneField(
        "Work",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="anime_profile",
    )
    format = models.CharField(max_length=64, blank=True)
    source_material = models.CharField(max_length=128, blank=True)
    episode_count = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "anime_profile"


class GalgameProfile(TimestampedModel):
    work = models.OneToOneField(
        "Work",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="galgame_profile",
    )
    playtime_minutes = models.PositiveIntegerField(null=True, blank=True)
    development_status = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "galgame_profile"


class Release(TimestampedModel):
    class DatePrecision(models.TextChoices):
        DAY = "day", "Day"
        MONTH = "month", "Month"
        YEAR = "year", "Year"
        RANGE = "range", "Range"
        UNKNOWN = "unknown", "Unknown"

    entity = models.OneToOneField(
        "Entity",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="release",
    )
    release_type = models.CharField(max_length=64, blank=True)
    date_start = models.DateField(null=True, blank=True)
    date_end = models.DateField(null=True, blank=True)
    date_precision = models.CharField(
        max_length=16,
        choices=DatePrecision.choices,
        default=DatePrecision.UNKNOWN,
    )
    date_raw = models.CharField(max_length=64, blank=True)
    platform = models.CharField(max_length=64, blank=True)
    region = models.CharField(max_length=16, blank=True)
    is_official = models.BooleanField(null=True, blank=True)
    is_patch = models.BooleanField(default=False)

    class Meta:
        db_table = "release"
        constraints = [
            models.CheckConstraint(
                condition=Q(date_end__isnull=True)
                | Q(date_start__isnull=True)
                | Q(date_start__lte=models.F("date_end")),
                name="ck_release_date_range",
            )
        ]


class ReleaseWork(models.Model):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary"
        INCLUDED = "included", "Included"
        BONUS = "bonus", "Bonus"

    release = models.ForeignKey(
        "Release",
        on_delete=models.CASCADE,
        related_name="work_links",
    )
    work = models.ForeignKey(
        "Work",
        on_delete=models.CASCADE,
        related_name="release_links",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PRIMARY)

    class Meta:
        db_table = "release_work"
        constraints = [
            models.UniqueConstraint(
                fields=["release", "work", "role"],
                name="uq_release_work_role",
            )
        ]


class Contributor(TimestampedModel):
    class Kind(models.TextChoices):
        PERSON = "person", "Person"
        ORGANIZATION = "organization", "Organization"
        UNKNOWN = "unknown", "Unknown"

    entity = models.OneToOneField(
        "Entity",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="contributor",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.UNKNOWN)

    class Meta:
        db_table = "contributor"


class Person(TimestampedModel):
    contributor = models.OneToOneField(
        "Contributor",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="person",
    )

    class Meta:
        db_table = "person"


class Organization(TimestampedModel):
    contributor = models.OneToOneField(
        "Contributor",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="organization",
    )

    class Meta:
        db_table = "organization"


class EntityName(TimestampedModel):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "Original"
        OFFICIAL = "official", "Official"
        ALIAS = "alias", "Alias"
        SHORT = "short", "Short"
        ROMANIZED = "romanized", "Romanized"
        TRANSLATED = "translated", "Translated"

    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="names")
    text = models.CharField(max_length=512)
    language = models.CharField(max_length=35, blank=True)
    script = models.CharField(max_length=4, blank=True)
    region = models.CharField(max_length=3, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    is_official = models.BooleanField(default=False)
    is_original = models.BooleanField(default=False)
    is_machine_generated = models.BooleanField(default=False)
    is_reviewed = models.BooleanField(default=False)
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity_names",
    )
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity_names",
    )

    class Meta:
        db_table = "entity_name"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "entity",
                    "text",
                    "language",
                    "kind",
                    "provider_record",
                    "observation",
                ],
                name="uq_entity_name_provenance",
                nulls_distinct=False,
            )
        ]
        indexes = [
            GinIndex(
                name="idx_entity_name_text", fields=["text"], opclasses=["gin_trgm_ops"]
            ),
            models.Index(
                fields=["entity", "language", "kind"],
                name="idx_entity_name_language",
            ),
        ]


class EntityDescription(TimestampedModel):
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="descriptions"
    )
    text = models.TextField()
    language = models.CharField(max_length=35, blank=True)
    is_official = models.BooleanField(default=False)
    is_machine_generated = models.BooleanField(default=False)
    is_reviewed = models.BooleanField(default=False)
    spoiler_level = models.PositiveSmallIntegerField(default=0)
    safety = models.CharField(
        max_length=16,
        choices=ContentSafety.choices,
        default=ContentSafety.UNKNOWN,
    )
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity_descriptions",
    )
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity_descriptions",
    )

    class Meta:
        db_table = "entity_description"
        constraints = [
            models.CheckConstraint(
                condition=Q(spoiler_level__lte=3),
                name="ck_description_spoiler_level",
            ),
            models.UniqueConstraint(
                fields=["entity", "language", "provider_record", "observation"],
                name="uq_entity_description_source",
                nulls_distinct=False,
            ),
        ]


class MediaAsset(TimestampedModel):
    Safety = ContentSafety

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.URLField(max_length=2048)
    media_type = models.CharField(max_length=64, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    safety = models.CharField(
        max_length=16,
        choices=Safety.choices,
        default=Safety.UNKNOWN,
    )
    spoiler_level = models.PositiveSmallIntegerField(default=0)
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="media_assets",
    )

    class Meta:
        db_table = "media_asset"
        constraints = [
            models.UniqueConstraint(
                fields=["url", "provider_record"],
                name="uq_media_asset_source",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(spoiler_level__lte=3),
                name="ck_media_spoiler_level",
            ),
        ]


class EntityMedia(models.Model):
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="media")
    asset = models.ForeignKey(
        "MediaAsset", on_delete=models.CASCADE, related_name="entity_links"
    )
    purpose = models.CharField(max_length=32, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity_media",
    )

    class Meta:
        db_table = "entity_media"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "asset", "purpose", "observation"],
                name="uq_entity_media_purpose",
                nulls_distinct=False,
            )
        ]


class IndexCollection(TimestampedModel):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "index_collection"
        ordering = ["slug"]


class IndexMembership(TimestampedModel):
    class State(models.TextChoices):
        LISTED = "listed", "Listed"
        UNLISTED = "unlisted", "Unlisted"
        SUPPRESSED = "suppressed", "Suppressed"

    collection = models.ForeignKey(
        "IndexCollection",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    entity = models.ForeignKey(
        "Entity",
        on_delete=models.CASCADE,
        related_name="index_memberships",
    )
    listing_state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.LISTED,
    )
    inclusion_reason = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "index_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "entity"],
                name="uq_index_membership",
            )
        ]
        indexes = [
            models.Index(
                fields=["collection", "listing_state", "-updated_at"],
                name="idx_membership_listing",
            )
        ]
