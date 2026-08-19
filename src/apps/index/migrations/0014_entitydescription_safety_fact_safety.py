from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('index', '0013_organization_person'),
    ]

    operations = [
        migrations.AddField(
            model_name='entitydescription',
            name='safety',
            field=models.CharField(choices=[('safe', 'Safe'), ('suggestive', 'Suggestive'), ('explicit', 'Explicit'), ('unknown', 'Unknown')], default='unknown', max_length=16),
        ),
        migrations.AddField(
            model_name='fact',
            name='safety',
            field=models.CharField(choices=[('safe', 'Safe'), ('suggestive', 'Suggestive'), ('explicit', 'Explicit'), ('unknown', 'Unknown')], default='unknown', max_length=16),
        ),
    ]
