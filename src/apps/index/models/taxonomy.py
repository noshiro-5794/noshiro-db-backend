from django.db import models


class Genre(models.Model):
    """Legacy projection retained for the Subject API compatibility window."""

    name = models.CharField(max_length=256, unique=True)

    class Meta:
        db_table = "genre"

    def __str__(self) -> str:
        return self.name


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
