from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0017_alter_usersubject_subject"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="adult_content_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="show_adult_content",
            field=models.BooleanField(default=False),
        ),
    ]
