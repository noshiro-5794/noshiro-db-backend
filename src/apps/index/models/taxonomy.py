from django.db import models

from .base import TimestampedModel


class TermAlias(TimestampedModel):
    class Origin(models.TextChoices):
        LEGACY_UNKNOWN = "legacy_unknown", "Legacy provenance unknown"
        PROVIDER = "provider", "Provider mapping"
        AI_PROPOSAL = "ai_proposal", "AI proposal"
        MANUAL = "manual", "Manual"

    vocabulary = models.SlugField(max_length=64)
    provider_namespace = models.ForeignKey(
        "ProviderNamespace",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="term_aliases",
    )
    term = models.ForeignKey(
        "Term",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="aliases",
    )
    source_text = models.CharField(max_length=256)
    normalized_key = models.CharField(max_length=256, db_index=True)
    preferred_term = models.CharField(max_length=256)
    language = models.CharField(max_length=35, blank=True)
    script = models.CharField(max_length=4, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=1)
    is_reviewed = models.BooleanField(default=False)
    origin = models.CharField(
        max_length=32,
        choices=Origin.choices,
        default=Origin.LEGACY_UNKNOWN,
    )

    class Meta:
        db_table = "index_term_alias"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "vocabulary",
                    "normalized_key",
                    "language",
                    "provider_namespace",
                ],
                name="uq_term_alias_key",
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(
                fields=["vocabulary", "normalized_key"],
                name="idx_term_alias_lookup",
            )
        ]

    def __str__(self) -> str:
        return f"{self.vocabulary}:{self.normalized_key} -> {self.preferred_term}"


class Taxonomy(models.Model):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "taxonomy"


class Term(models.Model):
    taxonomy = models.ForeignKey(
        "Taxonomy", on_delete=models.CASCADE, related_name="terms"
    )
    slug = models.SlugField(max_length=128)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        db_table = "taxonomy_term"
        constraints = [
            models.UniqueConstraint(
                fields=["taxonomy", "slug"], name="uq_taxonomy_term_slug"
            )
        ]


class TermLabel(models.Model):
    term = models.ForeignKey("Term", on_delete=models.CASCADE, related_name="labels")
    language = models.CharField(max_length=35)
    script = models.CharField(max_length=4, blank=True)
    text = models.CharField(max_length=256)
    is_preferred = models.BooleanField(default=False)

    class Meta:
        db_table = "taxonomy_term_label"
        constraints = [
            models.UniqueConstraint(
                fields=["term", "language", "script", "text"],
                name="uq_term_label",
            )
        ]


class TermMapping(models.Model):
    term = models.ForeignKey(
        "Term", on_delete=models.CASCADE, related_name="provider_mappings"
    )
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        related_name="taxonomy_mappings",
    )
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=1)

    class Meta:
        db_table = "taxonomy_term_mapping"
        constraints = [
            models.UniqueConstraint(
                fields=["term", "provider_record"], name="uq_term_provider_mapping"
            )
        ]


class EntityTerm(models.Model):
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="term_links"
    )
    term = models.ForeignKey(
        "Term", on_delete=models.CASCADE, related_name="entity_links"
    )
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="entity_terms",
    )
    relevance = models.DecimalField(max_digits=6, decimal_places=4, default=1)
    spoiler_level = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "entity_term"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "term", "observation"],
                name="uq_entity_term_source",
                nulls_distinct=False,
            )
        ]
