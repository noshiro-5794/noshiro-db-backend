import uuid

from django.db import models

from .base import TimestampedModel


class DataMigrationRun(TimestampedModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        PAUSED = "paused", "Paused"
        FAILED = "failed", "Failed"
        SUCCEEDED = "succeeded", "Succeeded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    command = models.CharField(max_length=128)
    version = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices)
    batch_size = models.PositiveIntegerField()
    parameters = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "data_migration_run"
        indexes = [
            models.Index(
                fields=["command", "status", "-created_at"],
                name="idx_data_migration_status",
            )
        ]


class DataMigrationCheckpoint(TimestampedModel):
    run = models.ForeignKey(
        "DataMigrationRun",
        on_delete=models.CASCADE,
        related_name="checkpoints",
    )
    stage = models.CharField(max_length=64)
    cursor = models.CharField(max_length=512, blank=True)
    upper_bound = models.CharField(max_length=512, blank=True)
    processed_count = models.PositiveBigIntegerField(default=0)
    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = "data_migration_checkpoint"
        constraints = [
            models.UniqueConstraint(
                fields=["run", "stage"],
                name="uq_data_migration_checkpoint",
            )
        ]
        indexes = [
            models.Index(
                fields=["run", "is_complete"],
                name="idx_data_migration_progress",
            )
        ]
