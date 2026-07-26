from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("index", "0005_calendarsubject_collection_doing"),
    ]

    operations = [
        migrations.AddField(
            model_name="calendarsubject",
            name="image_url",
            field=models.URLField(blank=True, max_length=1024),
        ),
    ]
