from django.contrib.postgres.operations import (
    AddIndexConcurrently,
    RemoveIndexConcurrently,
)
from django.db import migrations, models
from django.db.models import Count


SOURCE_MODELS = (
    ("Staff", "staff", "uq_staff_info_id_source"),
    ("Character", "character", "uq_character_info_id_source"),
    ("Episode", "episode", "uq_episode_info_id_source"),
    ("Subject", "subject", "uq_subject_info_id_source"),
    ("Anime", "anime", "uq_anime_info_id_source"),
    ("Galgame", "galgame", "uq_galgame_info_id_source"),
)


def ensure_source_identities_are_unique(apps, schema_editor) -> None:
    conflicts = []
    for model_name, _table_name, _constraint_name in SOURCE_MODELS:
        model = apps.get_model("index", model_name)
        duplicates = list(
            model.objects.values("info_source", "id_source")
            .annotate(row_count=Count("pk"))
            .filter(row_count__gt=1)
            .order_by("info_source", "id_source")[:10]
        )
        if duplicates:
            conflicts.append(f"{model_name}: {duplicates}")

    if conflicts:
        details = "; ".join(conflicts)
        raise RuntimeError(
            "Duplicate source identities must be reconciled before migration: "
            f"{details}"
        )


def source_identity_constraint(
    *,
    model_name: str,
    table_name: str,
    constraint_name: str,
) -> migrations.SeparateDatabaseAndState:
    return migrations.SeparateDatabaseAndState(
        database_operations=[
            migrations.RunSQL(
                sql=(
                    f'CREATE UNIQUE INDEX CONCURRENTLY "{constraint_name}" '
                    f'ON "{table_name}" ("info_source", "id_source")'
                ),
                reverse_sql=f'DROP INDEX CONCURRENTLY IF EXISTS "{constraint_name}"',
            ),
            migrations.RunSQL(
                sql=(
                    f'ALTER TABLE "{table_name}" '
                    f'ADD CONSTRAINT "{constraint_name}" '
                    f'UNIQUE USING INDEX "{constraint_name}"'
                ),
                reverse_sql=(
                    f'ALTER TABLE "{table_name}" '
                    f'DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                ),
            ),
        ],
        state_operations=[
            migrations.AddConstraint(
                model_name=model_name.lower(),
                constraint=models.UniqueConstraint(
                    fields=("info_source", "id_source"),
                    name=constraint_name,
                ),
            )
        ],
    )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("index", "0006_calendarsubject_image_url"),
    ]

    operations = [
        migrations.RunPython(
            ensure_source_identities_are_unique,
            reverse_code=migrations.RunPython.noop,
        ),
        *[
            source_identity_constraint(
                model_name=model_name,
                table_name=table_name,
                constraint_name=constraint_name,
            )
            for model_name, table_name, constraint_name in SOURCE_MODELS
        ],
        AddIndexConcurrently(
            model_name="subject",
            index=models.Index(
                fields=["id_source"],
                name="idx_subject_id_source",
            ),
        ),
        RemoveIndexConcurrently(
            model_name="calendarsubject",
            name="idx_cal_weekday_en",
        ),
        RemoveIndexConcurrently(
            model_name="subjectcharacteractorrelation",
            name="idx_subj_char_act_sc",
        ),
        RemoveIndexConcurrently(
            model_name="subjectsubjectrelation",
            name="idx_subj_subj_t",
        ),
        migrations.AlterUniqueTogether(
            name="animegenrerelation",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="animegenrerelation",
            constraint=models.UniqueConstraint(
                fields=("anime", "genre"),
                name="uq_anime_genre",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="galgamegenrerelation",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="galgamegenrerelation",
            constraint=models.UniqueConstraint(
                fields=("galgame", "genre"),
                name="uq_galgame_genre",
            ),
        ),
    ]
