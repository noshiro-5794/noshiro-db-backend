from django.db import migrations, models
from django.db.models import Count, Min


AIRING_EVENT_IDENTITY_FIELDS = (
    'work_id',
    'episode_entity_id',
    'starts_at',
    'timezone',
    'region',
    'weekday',
    'precision',
    'raw_value',
    'observation_id',
)


def remove_duplicate_airing_events(apps, schema_editor):
    AiringEvent = apps.get_model('index', 'AiringEvent')
    duplicate_groups = (
        AiringEvent.objects.using(schema_editor.connection.alias)
        .values(*AIRING_EVENT_IDENTITY_FIELDS)
        .annotate(keep_id=Min('id'), row_count=Count('id'))
        .filter(row_count__gt=1)
        .iterator(chunk_size=500)
    )
    for duplicate in duplicate_groups:
        identity = {
            field: duplicate[field]
            for field in AIRING_EVENT_IDENTITY_FIELDS
        }
        (
            AiringEvent.objects.using(schema_editor.connection.alias)
            .filter(**identity)
            .exclude(id=duplicate['keep_id'])
            .delete()
        )


class Migration(migrations.Migration):

    dependencies = [
        ('index', '0014_entitydescription_safety_fact_safety'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='resolutiondecision',
            name='uq_active_resolution_decision',
        ),
        migrations.AddField(
            model_name='resolutiondecision',
            name='language',
            field=models.CharField(blank=True, max_length=35),
        ),
        migrations.RunPython(
            remove_duplicate_airing_events,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='airingevent',
            constraint=models.UniqueConstraint(fields=('work', 'episode_entity', 'starts_at', 'timezone', 'region', 'weekday', 'precision', 'raw_value', 'observation'), name='uq_airing_event_source', nulls_distinct=False),
        ),
        migrations.AddConstraint(
            model_name='resolutiondecision',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('entity', 'predicate', 'language'), name='uq_active_resolution_decision'),
        ),
    ]
