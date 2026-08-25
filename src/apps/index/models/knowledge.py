import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .base import ContentSafety, TimestampedModel


class MappingRun(TimestampedModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey(
        "ProviderRevision",
        on_delete=models.PROTECT,
        related_name="mapping_runs",
    )
    mapper = models.CharField(max_length=128)
    mapper_version = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mapping_run"
        indexes = [
            models.Index(
                fields=["revision", "mapper", "-created_at"],
                name="idx_mapping_run_revision",
            )
        ]


class Observation(TimestampedModel):
    class Origin(models.TextChoices):
        MAPPED = "mapped", "Mapped"
        LEGACY = "legacy", "Legacy"
        MANUAL = "manual", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        related_name="observations",
    )
    mapping_run = models.ForeignKey(
        "MappingRun",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="observations",
    )
    origin = models.CharField(max_length=16, choices=Origin.choices)
    schema_name = models.CharField(max_length=128)
    schema_version = models.CharField(max_length=64)
    normalized_data = models.JSONField()
    normalized_hash = models.CharField(max_length=64)
    observed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "provider_observation"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "provider_record",
                    "mapping_run",
                    "schema_name",
                    "normalized_hash",
                ],
                name="uq_observation_mapping_hash",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(origin="legacy", mapping_run__isnull=True)
                | Q(mapping_run__isnull=False),
                name="ck_observation_mapping_origin",
            ),
        ]
        indexes = [
            models.Index(
                fields=["provider_record", "-observed_at"],
                name="idx_observation_record_time",
            )
        ]


class CurrentObservation(TimestampedModel):
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.CASCADE,
        related_name="current_observations",
    )
    mapper = models.CharField(max_length=128)
    schema_name = models.CharField(max_length=128)
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        related_name="current_projections",
    )

    class Meta:
        db_table = "provider_current_observation"
        constraints = [
            models.UniqueConstraint(
                fields=["provider_record", "mapper", "schema_name"],
                name="uq_current_observation_mapper",
            )
        ]


class Predicate(TimestampedModel):
    class ValueType(models.TextChoices):
        STRING = "string", "String"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        DATE = "date", "Date"
        ENTITY = "entity", "Entity"
        JSON = "json", "JSON"

    slug = models.SlugField(max_length=128, unique=True)
    name = models.CharField(max_length=256)
    value_type = models.CharField(max_length=16, choices=ValueType.choices)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "predicate"


class Fact(TimestampedModel):
    class Status(models.TextChoices):
        CANDIDATE = "candidate", "Candidate"
        SELECTED = "selected", "Selected"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity = models.ForeignKey("Entity", on_delete=models.CASCADE, related_name="facts")
    predicate = models.ForeignKey(
        "Predicate", on_delete=models.PROTECT, related_name="facts"
    )
    value = models.JSONField()
    value_hash = models.CharField(max_length=64)
    language = models.CharField(max_length=35, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.CANDIDATE,
    )
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    spoiler_level = models.PositiveSmallIntegerField(default=0)
    safety = models.CharField(
        max_length=16,
        choices=ContentSafety.choices,
        default=ContentSafety.UNKNOWN,
    )
    is_machine_generated = models.BooleanField(default=False)

    class Meta:
        db_table = "fact"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "predicate", "value_hash", "language"],
                name="uq_fact_value",
            ),
            models.CheckConstraint(
                condition=Q(spoiler_level__lte=3), name="ck_fact_spoiler_level"
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0, confidence__lte=1),
                name="ck_fact_confidence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["entity", "predicate", "status"], name="idx_fact_resolution"
            )
        ]


class FactEvidence(TimestampedModel):
    fact = models.ForeignKey("Fact", on_delete=models.CASCADE, related_name="evidence")
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        related_name="fact_evidence",
    )
    json_pointer = models.CharField(max_length=512, blank=True)
    note = models.CharField(max_length=512, blank=True)

    class Meta:
        db_table = "fact_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["fact", "observation", "json_pointer"],
                name="uq_fact_evidence_pointer",
            )
        ]


class MetricSnapshot(models.Model):
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="metric_snapshots"
    )
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        related_name="metric_snapshots",
    )
    metric = models.CharField(max_length=64)
    value = models.DecimalField(max_digits=20, decimal_places=6)
    sample_size = models.PositiveBigIntegerField(null=True, blank=True)
    observed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "metric_snapshot"
        constraints = [
            models.UniqueConstraint(
                fields=["provider_record", "metric", "observed_at"],
                name="uq_metric_snapshot_time",
            )
        ]
        indexes = [
            models.Index(
                fields=["entity", "metric", "-observed_at"],
                name="idx_metric_entity_time",
            )
        ]


class ContentRating(TimestampedModel):
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="content_ratings"
    )
    system = models.CharField(max_length=64)
    value = models.CharField(max_length=64)
    region = models.CharField(max_length=16, blank=True)
    minimum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        related_name="content_ratings",
    )
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="content_ratings",
    )

    class Meta:
        db_table = "content_rating"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "entity",
                    "system",
                    "value",
                    "region",
                    "provider_record",
                    "observation",
                ],
                name="uq_content_rating_source",
                nulls_distinct=False,
            )
        ]


class ExternalLink(TimestampedModel):
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="external_links"
    )
    url = models.URLField(max_length=2048)
    label = models.CharField(max_length=128, blank=True)
    link_type = models.CharField(max_length=64, blank=True)
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="external_links",
    )
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="external_links",
    )

    class Meta:
        db_table = "external_link"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "url", "provider_record", "observation"],
                name="uq_external_link_source",
                nulls_distinct=False,
            )
        ]


class EntityRelation(TimestampedModel):
    from_entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="outgoing_entity_relations"
    )
    to_entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="incoming_entity_relations"
    )
    relation_type = models.SlugField(max_length=128)
    qualifiers = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "entity_relation"
        constraints = [
            models.UniqueConstraint(
                fields=["from_entity", "to_entity", "relation_type"],
                name="uq_entity_relation_type",
            ),
            models.CheckConstraint(
                condition=~Q(from_entity=models.F("to_entity")),
                name="ck_entity_relation_not_self",
            ),
        ]
        indexes = [
            models.Index(
                fields=["from_entity", "relation_type"],
                name="idx_entity_relation_from",
            )
        ]


class EntityRelationEvidence(TimestampedModel):
    relation = models.ForeignKey(
        "EntityRelation", on_delete=models.CASCADE, related_name="evidence"
    )
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        related_name="relation_evidence",
    )
    json_pointer = models.CharField(max_length=512, blank=True)
    raw_relation = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "entity_relation_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["relation", "observation", "json_pointer"],
                name="uq_entity_relation_evidence",
            )
        ]


class ReleaseWorkEvidence(TimestampedModel):
    release_work = models.ForeignKey(
        "ReleaseWork",
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        related_name="release_work_evidence",
    )
    json_pointer = models.CharField(max_length=512, blank=True)
    raw_role = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "release_work_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["release_work", "observation", "json_pointer"],
                name="uq_release_work_evidence",
            )
        ]


class Credit(TimestampedModel):
    work = models.ForeignKey("Work", on_delete=models.CASCADE, related_name="credits")
    contributor = models.ForeignKey(
        "Contributor", on_delete=models.CASCADE, related_name="credits"
    )
    role = models.CharField(max_length=256)
    credited_as = models.CharField(max_length=512, blank=True)
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="credits",
    )

    class Meta:
        db_table = "credit"
        constraints = [
            models.UniqueConstraint(
                fields=["work", "contributor", "role", "credited_as", "observation"],
                name="uq_credit_provenance",
                nulls_distinct=False,
            )
        ]


class Appearance(TimestampedModel):
    work = models.ForeignKey(
        "Work", on_delete=models.CASCADE, related_name="appearances"
    )
    character_entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="character_appearances"
    )
    role = models.CharField(max_length=128, blank=True)
    spoiler_level = models.PositiveSmallIntegerField(default=0)
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appearances",
    )

    class Meta:
        db_table = "appearance"
        constraints = [
            models.UniqueConstraint(
                fields=["work", "character_entity", "role", "observation"],
                name="uq_appearance_provenance",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=Q(spoiler_level__lte=3),
                name="ck_appearance_spoiler_level",
            ),
        ]


class VoicePerformance(TimestampedModel):
    appearance = models.ForeignKey(
        "Appearance", on_delete=models.CASCADE, related_name="voice_performances"
    )
    contributor = models.ForeignKey(
        "Contributor", on_delete=models.CASCADE, related_name="voice_performances"
    )
    language = models.CharField(max_length=35, blank=True)
    credited_as = models.CharField(max_length=512, blank=True)
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="voice_performances",
    )

    class Meta:
        db_table = "voice_performance"
        constraints = [
            models.UniqueConstraint(
                fields=["appearance", "contributor", "language", "observation"],
                name="uq_voice_performance_source",
                nulls_distinct=False,
            )
        ]


class AiringEvent(TimestampedModel):
    class Precision(models.TextChoices):
        MINUTE = "minute", "Minute"
        DAY = "day", "Day"
        WEEKDAY = "weekday", "Weekday"
        UNKNOWN = "unknown", "Unknown"

    work = models.ForeignKey(
        "Work", on_delete=models.CASCADE, related_name="airing_events"
    )
    episode_entity = models.ForeignKey(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="airing_events",
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, blank=True)
    region = models.CharField(max_length=16, blank=True)
    weekday = models.PositiveSmallIntegerField(null=True, blank=True)
    precision = models.CharField(
        max_length=16,
        choices=Precision.choices,
        default=Precision.UNKNOWN,
    )
    raw_value = models.CharField(max_length=256, blank=True)
    collection_doing = models.PositiveIntegerField(default=0)
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="airing_events",
    )

    class Meta:
        db_table = "airing_event"
        constraints = [
            models.CheckConstraint(
                condition=Q(weekday__isnull=True) | Q(weekday__range=(1, 7)),
                name="ck_airing_weekday",
            ),
            models.UniqueConstraint(
                fields=[
                    "work",
                    "episode_entity",
                    "starts_at",
                    "timezone",
                    "region",
                    "weekday",
                    "precision",
                    "raw_value",
                    "observation",
                ],
                name="uq_airing_event_source",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(fields=["starts_at"], name="idx_airing_starts_at"),
            models.Index(fields=["weekday"], name="idx_airing_weekday"),
        ]
