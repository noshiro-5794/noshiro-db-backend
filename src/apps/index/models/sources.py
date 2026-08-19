import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .base import TimestampedModel


class Provider(TimestampedModel):
    class UsagePolicy(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        ALLOWED = "allowed", "Allowed"
        RESTRICTED = "restricted", "Restricted"
        FORBIDDEN = "forbidden", "Forbidden"

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    base_url = models.URLField(max_length=1024, blank=True)
    terms_url = models.URLField(max_length=1024, blank=True)
    attribution_url = models.URLField(max_length=1024, blank=True)
    license_name = models.CharField(max_length=128, blank=True)
    storage_policy = models.CharField(
        max_length=16,
        choices=UsagePolicy.choices,
        default=UsagePolicy.UNKNOWN,
    )
    redistribution_policy = models.CharField(
        max_length=16,
        choices=UsagePolicy.choices,
        default=UsagePolicy.UNKNOWN,
    )
    commercial_use_policy = models.CharField(
        max_length=16,
        choices=UsagePolicy.choices,
        default=UsagePolicy.UNKNOWN,
    )
    ai_usage_policy = models.CharField(
        max_length=16,
        choices=UsagePolicy.choices,
        default=UsagePolicy.UNKNOWN,
    )
    terms_checked_at = models.DateTimeField(null=True, blank=True)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "provider"
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


class ProviderNamespace(TimestampedModel):
    class ResourceType(models.TextChoices):
        SUBJECT = "subject", "Subject"
        EPISODE = "episode", "Episode"
        PERSON = "person", "Person"
        CHARACTER = "character", "Character"
        ORGANIZATION = "organization", "Organization"
        RELEASE = "release", "Release"
        SCHEDULE = "schedule", "Schedule"
        TAXONOMY = "taxonomy", "Taxonomy"
        COLLECTION = "collection", "Collection snapshot"

    provider = models.ForeignKey(
        "Provider",
        on_delete=models.PROTECT,
        related_name="namespaces",
    )
    slug = models.SlugField(max_length=64)
    resource_type = models.CharField(max_length=32, choices=ResourceType.choices)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = "provider_namespace"
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "slug"],
                name="uq_provider_namespace_slug",
            )
        ]
        ordering = ["provider__slug", "slug"]

    def __str__(self) -> str:
        return f"{self.provider.slug}:{self.slug}"

    @property
    def source(self):
        """Compatibility alias for pre-Provider synchronizer code."""
        return self.provider


class ProviderRecord(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MISSING = "missing", "Missing"
        DELETED = "deleted", "Deleted"

    class Origin(models.TextChoices):
        LEGACY_PROJECTION = "legacy", "Legacy projection"
        API = "api", "API"
        DUMP = "dump", "Dump"
        MANUAL = "manual", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    namespace = models.ForeignKey(
        "ProviderNamespace",
        on_delete=models.PROTECT,
        related_name="records",
    )
    external_id = models.CharField(max_length=255)
    canonical_url = models.URLField(max_length=1024, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    origin = models.CharField(max_length=16, choices=Origin.choices)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    latest_payload_hash = models.CharField(max_length=64, blank=True)
    latest_revision = models.ForeignKey(
        "ProviderRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "provider_record"
        constraints = [
            models.UniqueConstraint(
                fields=["namespace", "external_id"],
                name="uq_provider_record_external_id",
            )
        ]
        indexes = [
            models.Index(
                fields=["namespace", "status"],
                name="idx_provider_record_ns_status",
            ),
            models.Index(fields=["last_seen_at"], name="idx_provider_record_seen"),
        ]

    def __str__(self) -> str:
        return f"{self.namespace}:{self.external_id}"


class ProviderRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    payload = models.JSONField()
    payload_hash = models.CharField(max_length=64)
    schema_version = models.CharField(max_length=64, blank=True)
    response_metadata = models.JSONField(default=dict, blank=True)
    upstream_updated_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "provider_revision"
        constraints = [
            models.UniqueConstraint(
                fields=["record", "payload_hash"],
                name="uq_provider_revision_hash",
            )
        ]
        indexes = [
            models.Index(
                fields=["record", "-fetched_at"],
                name="idx_provider_revision_fetched",
            )
        ]
        ordering = ["-fetched_at"]

    def __str__(self) -> str:
        return f"{self.record}:{self.payload_hash[:12]}"


class ExternalIdentityBase(TimestampedModel):
    """Legacy binding retained until Subject-based API compatibility is removed."""

    class MatchMethod(models.TextChoices):
        LEGACY = "legacy", "Legacy backfill"
        PROVIDER = "provider", "Provider record"
        EXTERNAL_ID = "external_id", "Verified external ID"
        MANUAL = "manual", "Manual"
        REVIEWED_AI = "reviewed_ai", "Reviewed AI proposal"

    source_record = models.OneToOneField(
        "ProviderRecord",
        on_delete=models.PROTECT,
        related_name="+",
    )
    match_method = models.CharField(max_length=16, choices=MatchMethod.choices)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    is_primary = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class SubjectExternalIdentity(ExternalIdentityBase):
    subject = models.ForeignKey(
        "Subject",
        on_delete=models.CASCADE,
        related_name="external_identities",
    )

    class Meta:
        db_table = "subject_external_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["subject"],
                condition=models.Q(is_primary=True),
                name="uq_subject_primary_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="ck_subject_identity_confidence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["subject", "is_primary"],
                name="idx_subject_identity_primary",
            )
        ]


class EpisodeExternalIdentity(ExternalIdentityBase):
    episode = models.ForeignKey(
        "Episode",
        on_delete=models.CASCADE,
        related_name="external_identities",
    )

    class Meta:
        db_table = "episode_external_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["episode"],
                condition=models.Q(is_primary=True),
                name="uq_episode_primary_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="ck_episode_identity_confidence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["episode", "is_primary"],
                name="idx_episode_identity_primary",
            )
        ]


class StaffExternalIdentity(ExternalIdentityBase):
    staff = models.ForeignKey(
        "Staff",
        on_delete=models.CASCADE,
        related_name="external_identities",
    )

    class Meta:
        db_table = "staff_external_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["staff"],
                condition=models.Q(is_primary=True),
                name="uq_staff_primary_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="ck_staff_identity_confidence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["staff", "is_primary"],
                name="idx_staff_identity_primary",
            )
        ]


class CharacterExternalIdentity(ExternalIdentityBase):
    character = models.ForeignKey(
        "Character",
        on_delete=models.CASCADE,
        related_name="external_identities",
    )

    class Meta:
        db_table = "character_external_identity"
        constraints = [
            models.UniqueConstraint(
                fields=["character"],
                condition=models.Q(is_primary=True),
                name="uq_character_primary_identity",
            ),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="ck_character_identity_confidence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["character", "is_primary"],
                name="idx_character_identity_primary",
            )
        ]


# Transitional Python aliases keep the deployed Subject synchronizers operational while
# the canonical ingestion path moves to ProviderRepresentation.
CatalogSource = Provider
SourceNamespace = ProviderNamespace
SourceRecord = ProviderRecord
SourceRecordRevision = ProviderRevision
