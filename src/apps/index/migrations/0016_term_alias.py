import re
import unicodedata

from django.db import migrations, models


def normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"\s+", " ", value)


def copy_sync_name_mappings(apps, schema_editor):
    TermAlias = apps.get_model("index", "TermAlias")
    NameMapping = apps.get_model("sync", "NameMapping")
    aliases = [
        TermAlias(
            vocabulary="legacy",
            provider_namespace=None,
            source_text=mapping.external_name,
            normalized_key=normalize_key(mapping.external_name),
            preferred_term=mapping.internal_name,
            language="",
            script="",
            confidence=1,
            is_reviewed=False,
        )
        for mapping in NameMapping.objects.iterator(chunk_size=1000)
    ]
    TermAlias.objects.bulk_create(aliases, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("index", "0015_remove_resolutiondecision_uq_active_resolution_decision_and_more"),
        ("sync", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TermAlias",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("vocabulary", models.SlugField(max_length=64)),
                (
                    "provider_namespace",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.PROTECT,
                        related_name="term_aliases",
                        to="index.providernamespace",
                    ),
                ),
                ("source_text", models.CharField(max_length=256)),
                ("normalized_key", models.CharField(db_index=True, max_length=256)),
                ("preferred_term", models.CharField(max_length=256)),
                ("language", models.CharField(blank=True, max_length=35)),
                ("script", models.CharField(blank=True, max_length=4)),
                (
                    "confidence",
                    models.DecimalField(
                        decimal_places=4,
                        default=1,
                        max_digits=5,
                    ),
                ),
                ("is_reviewed", models.BooleanField(default=False)),
            ],
            options={
                "db_table": "index_term_alias",
            },
        ),
        migrations.AddConstraint(
            model_name="termalias",
            constraint=models.UniqueConstraint(
                fields=(
                    "vocabulary",
                    "normalized_key",
                    "language",
                    "provider_namespace",
                ),
                name="uq_term_alias_key",
            ),
        ),
        migrations.AddIndex(
            model_name="termalias",
            index=models.Index(
                fields=["vocabulary", "normalized_key"],
                name="idx_term_alias_lookup",
            ),
        ),
        migrations.RunPython(copy_sync_name_mappings, migrations.RunPython.noop),
    ]
