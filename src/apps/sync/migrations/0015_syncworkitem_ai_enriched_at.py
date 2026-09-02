from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sync", "0014_index_campaign_execution"),
    ]

    operations = [
        migrations.AddField(
            model_name="syncworkitem",
            name="ai_enriched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
