from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0010_userprofile_preferences"),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddIndex(
            model_name="review",
            index=models.Index(fields=["-updated_at"], name="idx_review_updated"),
        ),
    ]
