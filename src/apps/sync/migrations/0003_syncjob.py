import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sync", "0002_syncerror_syncstate_fail_count_alter_syncstate_shard_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SyncJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("job_type", models.CharField(choices=[("subject_bangumi", "Subject by Bangumi"), ("subject_resync", "Subject resync"), ("calendar", "Calendar"), ("incremental", "Incremental")], max_length=64)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed")], default="queued", max_length=32)),
                ("celery_task_id", models.CharField(blank=True, max_length=256)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                ("current_label", models.CharField(blank=True, max_length=256)),
                ("total_count", models.IntegerField(default=0)),
                ("processed_count", models.IntegerField(default=0)),
                ("synced_count", models.IntegerField(default=0)),
                ("skipped_count", models.IntegerField(default=0)),
                ("failed_count", models.IntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "sync_job",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="syncjob",
            index=models.Index(fields=["status", "created_at"], name="idx_sync_job_status_created"),
        ),
        migrations.AddIndex(
            model_name="syncjob",
            index=models.Index(fields=["job_type", "created_at"], name="idx_sync_job_type_created"),
        ),
        migrations.AddIndex(
            model_name="syncjob",
            index=models.Index(fields=["celery_task_id"], name="idx_sync_job_celery_task"),
        ),
    ]
