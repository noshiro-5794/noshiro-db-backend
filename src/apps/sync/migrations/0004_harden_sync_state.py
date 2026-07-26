from django.contrib.postgres.operations import RemoveIndexConcurrently
from django.db import migrations, models
from django.db.models import Q


def ensure_sync_counters_are_valid(apps, schema_editor) -> None:
    sync_error = apps.get_model("sync", "SyncError")
    sync_state = apps.get_model("sync", "SyncState")
    sync_job = apps.get_model("sync", "SyncJob")

    invalid_error_ids = list(
        sync_error.objects.filter(retry_count__lt=0).values_list("pk", flat=True)[:10]
    )
    invalid_state_ids = list(
        sync_state.objects.filter(
            Q(current_id__lt=0)
            | Q(end_id__lt=0)
            | Q(fail_count__lt=0)
            | ~Q(status__in=("idle", "running", "finished", "failed"))
        ).values_list("pk", flat=True)[:10]
    )
    invalid_job_ids = list(
        sync_job.objects.filter(
            Q(total_count__lt=0)
            | Q(processed_count__lt=0)
            | Q(synced_count__lt=0)
            | Q(skipped_count__lt=0)
            | Q(failed_count__lt=0)
        ).values_list("pk", flat=True)[:10]
    )

    if invalid_error_ids or invalid_state_ids or invalid_job_ids:
        raise RuntimeError(
            "Sync rows must be corrected before applying non-negative counters. "
            f"Invalid SyncError IDs: {invalid_error_ids}; "
            f"SyncState IDs: {invalid_state_ids}; SyncJob IDs: {invalid_job_ids}."
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("sync", "0003_syncjob"),
    ]

    operations = [
        migrations.RunPython(
            ensure_sync_counters_are_valid,
            reverse_code=migrations.RunPython.noop,
        ),
        RemoveIndexConcurrently(
            model_name="namemapping",
            name="idx_name_mapping",
        ),
        RemoveIndexConcurrently(
            model_name="syncerror",
            name="idx_name_id",
        ),
        RemoveIndexConcurrently(
            model_name="syncstate",
            name="idx_name_shard",
        ),
        migrations.AlterField(
            model_name="syncerror",
            name="retry_count",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="syncjob",
            name="failed_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="syncjob",
            name="processed_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="syncjob",
            name="skipped_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="syncjob",
            name="synced_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="syncjob",
            name="total_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="syncstate",
            name="current_id",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="syncstate",
            name="end_id",
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterField(
            model_name="syncstate",
            name="fail_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="syncstate",
            name="status",
            field=models.CharField(
                choices=(
                    ("idle", "Idle"),
                    ("running", "Running"),
                    ("finished", "Finished"),
                    ("failed", "Failed"),
                ),
                default="running",
                max_length=16,
            ),
        ),
    ]
