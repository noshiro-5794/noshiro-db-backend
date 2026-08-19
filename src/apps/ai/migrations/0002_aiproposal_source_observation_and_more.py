import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0001_initial'),
        ('index', '0014_entitydescription_safety_fact_safety'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiproposal',
            name='source_observation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ai_proposals', to='index.observation'),
        ),
        migrations.AddField(
            model_name='aiproposal',
            name='target_entity',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ai_proposals', to='index.entity'),
        ),
        migrations.AlterField(
            model_name='aiproposal',
            name='match_candidate',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ai_proposals', to='index.matchcandidate'),
        ),
    ]
