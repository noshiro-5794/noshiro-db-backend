import uuid

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


# Backwards-compatible aliases used by the provider synchronizers.
CatalogSource = Provider
SourceNamespace = ProviderNamespace
SourceRecord = ProviderRecord
SourceRecordRevision = ProviderRevision
