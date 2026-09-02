import uuid

from django.db import models


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
        ANILIST_IMPORT = "anilist_import", "AniList import"
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


class SyncCampaign(models.Model):
    """Durable, shardable campaign for provider-wide synchronization."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        DISCOVERING = "discovering", "Discovering"
        FETCHING = "fetching", "Fetching"
        MAPPING = "mapping", "Mapping"
        NORMALIZING = "normalizing", "Normalizing"
        RECONCILING = "reconciling", "Reconciling"
        ENRICHING = "enriching", "Enriching"
        REVIEWING = "reviewing", "Reviewing"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class AIMode(models.TextChoices):
        OFF = "off", "Off"
        SHADOW = "shadow", "Shadow"
        ASSISTED = "assisted", "Assisted"
        REQUIRED = "required", "Required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.OneToOneField(
        "ai.AgentRun",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sync_campaign",
    )
    provider_slug = models.CharField(max_length=64)
    campaign_type = models.CharField(max_length=32)
    idempotency_key = models.CharField(max_length=128, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    ai_mode = models.CharField(
        max_length=16, choices=AIMode.choices, default=AIMode.SHADOW
    )
    parameters = models.JSONField(default=dict, blank=True)
    total_items = models.PositiveIntegerField(default=0)
    processed_items = models.PositiveIntegerField(default=0)
    synced_items = models.PositiveIntegerField(default=0)
    skipped_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    quality_report = models.JSONField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    error = models.TextField(blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.CharField(max_length=128, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sync_campaign"
        indexes = [
            models.Index(
                fields=["provider_slug", "status"], name="idx_sync_camp_prov_status"
            ),
            models.Index(
                fields=["status", "-created_at"], name="idx_sync_campaign_status"
            ),
            models.Index(
                fields=["status", "next_run_at"], name="idx_sync_campaign_next_run"
            ),
            models.Index(
                fields=["status", "lease_expires_at"], name="idx_sync_campaign_lease"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["provider_slug", "campaign_type", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uq_sync_campaign_idempotency",
            )
        ]


class SyncWorkItem(models.Model):
    """One idempotent unit of work inside a SyncCampaign."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        "SyncCampaign", on_delete=models.CASCADE, related_name="work_items"
    )
    shard = models.PositiveIntegerField(default=0)
    cursor = models.CharField(max_length=512)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    provider_record = models.ForeignKey(
        "index.ProviderRecord",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sync_work_items",
    )
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    attempt = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    lease_owner = models.CharField(max_length=128, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    ai_processed_at = models.DateTimeField(null=True, blank=True)
    ai_enriched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sync_work_item"
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "shard", "cursor"],
                name="uq_sync_work_item_cursor",
            )
        ]
        indexes = [
            models.Index(fields=["campaign", "status"], name="idx_sync_wi_camp_status"),
            models.Index(
                fields=["status", "lease_expires_at"], name="idx_sync_wi_lease"
            ),
            models.Index(
                fields=["campaign", "status", "next_retry_at"],
                name="idx_sync_wi_retry",
            ),
        ]
