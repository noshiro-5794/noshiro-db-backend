import django.db.models.deletion
from django.db import migrations, models


def backfill_contributor_subtypes(apps, schema_editor):
    tables = {
        "contributor": schema_editor.quote_name("contributor"),
        "person": schema_editor.quote_name("person"),
        "organization": schema_editor.quote_name("organization"),
    }
    with schema_editor.connection.cursor() as cursor:
        for kind in ("person", "organization"):
            cursor.execute(
                f"""
                INSERT INTO {tables[kind]}
                    (contributor_id, created_at, updated_at)
                SELECT entity_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                FROM {tables["contributor"]}
                WHERE kind = %s
                ON CONFLICT (contributor_id) DO NOTHING
                """,
                [kind],
            )


class Migration(migrations.Migration):

    dependencies = [
        ('index', '0012_reversible_entity_redirects'),
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contributor', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='organization', serialize=False, to='index.contributor')),
            ],
            options={
                'db_table': 'organization',
            },
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('contributor', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='person', serialize=False, to='index.contributor')),
            ],
            options={
                'db_table': 'person',
            },
        ),
        migrations.RunPython(
            backfill_contributor_subtypes,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
