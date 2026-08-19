import uuid

from django.db import models


class NameMapping(models.Model):
    external_name = models.CharField(max_length=256)
    internal_name = models.CharField(max_length=256)

    class Meta:
        db_table = "name_mapping"
        constraints = [
            models.UniqueConstraint(fields=["external_name"], name="uq_name_mapping"),
        ]

    def __str__(self) -> str:
        return f"{self.external_name} -> {self.internal_name}"


class SyncState(models.Model):
    class Status(models.TextChoices):
        IDLE = "idle", "Idle"
        RUNNING = "running", "Running"
        FINISHED = "finished", "Finished"
        FAILED = "failed", "Failed"

    task_name = models.CharField(max_length=256)
    shard = models.CharField(max_length=256)
    current_id = models.PositiveIntegerField(default=0)
    end_id = models.PositiveIntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    fail_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sync_state"
        constraints = [
            models.UniqueConstraint(fields=["task_name", "shard"], name="uq_name_shard")
        ]

    def __str__(self) -> str:
        return f"{self.task_name}:{self.current_id} [{self.status}]"


class SyncError(models.Model):
    task_name = models.CharField(max_length=256)
    entity_id = models.IntegerField()
    retry_count = models.PositiveIntegerField(default=1)
    first_occurred_at = models.DateTimeField(auto_now_add=True)
    last_occurred_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sync_error"
        constraints = [
            models.UniqueConstraint(
                fields=["task_name", "entity_id"], name="uq_name_id"
            )
        ]

    def __str__(self) -> str:
        return f"{self.task_name}:{self.entity_id}"


class SyncJob(models.Model):
    class JobType(models.TextChoices):
        SUBJECT_BANGUMI = "subject_bangumi", "Subject by Bangumi"
        SUBJECT_RESYNC = "subject_resync", "Subject resync"
        VNDB_IMPORT = "vndb_import", "VNDB import"
        CALENDAR = "calendar", "Calendar"
        INCREMENTAL = "incremental", "Incremental"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=64, choices=JobType.choices)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    celery_task_id = models.CharField(max_length=256, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    current_label = models.CharField(max_length=256, blank=True)
    total_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    synced_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    attempt = models.PositiveIntegerField(default=0)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.CharField(max_length=256, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sync_job"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"], name="idx_sync_job_status_created"
            ),
            models.Index(
                fields=["job_type", "created_at"], name="idx_sync_job_type_created"
            ),
            models.Index(fields=["celery_task_id"], name="idx_sync_job_celery_task"),
            models.Index(
                fields=["status", "lease_expires_at"],
                name="idx_sync_job_lease",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.job_type}:{self.status}:{self.id}"
