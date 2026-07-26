from datetime import date

from django.db import migrations, models
from django.db.models import Q


def ensure_watch_dates_are_valid(apps, schema_editor) -> None:
    user_subject = apps.get_model("users", "UserSubject")
    invalid_rows = []

    for row_id, start_value, end_value in user_subject.objects.values_list(
        "pk",
        "watch_start_date",
        "watch_end_date",
    ).iterator(chunk_size=2_000):
        try:
            start_date = date.fromisoformat(start_value) if start_value else None
            end_date = date.fromisoformat(end_value) if end_value else None
        except (TypeError, ValueError):
            invalid_rows.append(row_id)
            if len(invalid_rows) >= 10:
                break
            continue

        if start_date and end_date and start_date > end_date:
            invalid_rows.append(row_id)
            if len(invalid_rows) >= 10:
                break

    if invalid_rows:
        raise RuntimeError(
            "UserSubject watch dates must be valid ISO dates with start <= end. "
            f"Invalid row IDs: {invalid_rows}."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0014_remove_redundant_indexes"),
    ]

    operations = [
        migrations.RunPython(
            ensure_watch_dates_are_valid,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_start_date" DROP NOT NULL'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_start_date" SET NOT NULL'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_start_date" TYPE date '
                        'USING NULLIF("watch_start_date", \'\')::date'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_start_date" TYPE varchar(16) '
                        'USING COALESCE("watch_start_date"::text, \'\')'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_end_date" DROP NOT NULL'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_end_date" SET NOT NULL'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_end_date" TYPE date '
                        'USING NULLIF("watch_end_date", \'\')::date'
                    ),
                    reverse_sql=(
                        'ALTER TABLE "user_subject" '
                        'ALTER COLUMN "watch_end_date" TYPE varchar(16) '
                        'USING COALESCE("watch_end_date"::text, \'\')'
                    ),
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="usersubject",
                    name="watch_start_date",
                    field=models.DateField(blank=True, null=True),
                ),
                migrations.AlterField(
                    model_name="usersubject",
                    name="watch_end_date",
                    field=models.DateField(blank=True, null=True),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="usersubject",
            constraint=models.CheckConstraint(
                condition=Q(watch_start_date__isnull=True)
                | Q(watch_end_date__isnull=True)
                | Q(watch_start_date__lte=models.F("watch_end_date")),
                name="ck_watch_date_range",
            ),
        ),
    ]
