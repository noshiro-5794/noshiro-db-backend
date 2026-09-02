import uuid

from django.db import models
from django.db.models import Q


class AgentSession(models.Model):
    """User-facing conversation container; it is not permanent agent memory."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="agent_sessions"
    )
    title = models.CharField(max_length=256, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_session"
        indexes = [
            models.Index(fields=["user", "-updated_at"], name="idx_agent_session_user")
        ]


class AgentRun(models.Model):
    """Durable top-level execution for an admin, sync, user, or eval workflow."""

    class Kind(models.TextChoices):
        ADMIN_SYNC = "admin_sync", "Admin sync"
        ADMIN_ENRICH = "admin_enrich", "Admin enrichment"
        USER_AGENT = "user_agent", "User agent"
        EVALUATION = "evaluation", "Evaluation"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        WAITING = "waiting", "Waiting"
        PAUSED = "paused", "Paused"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    session = models.ForeignKey(
        "AgentSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    requested_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="requested_agent_runs",
    )
    title = models.CharField(max_length=256, blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True)
    idempotency_scope = models.CharField(max_length=128, default="system")
    trace_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    checkpoint = models.JSONField(default=dict, blank=True)
    budget = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_run"
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_scope", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uq_agent_run_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["kind", "status"], name="idx_agent_run_kind_status"),
            models.Index(
                fields=["status", "-created_at"], name="idx_agent_run_status_created"
            ),
        ]


class AgentStep(models.Model):
    """Persisted node in an explicit harness workflow."""

    class Kind(models.TextChoices):
        PLAN = "plan", "Plan"
        RETRIEVE = "retrieve", "Retrieve"
        TOOL = "tool", "Tool"
        MODEL = "model", "Model"
        SKILL = "skill", "Skill"
        VALIDATE = "validate", "Validate"
        APPROVAL = "approval", "Approval"
        APPLY = "apply", "Apply"
        VERIFY = "verify", "Verify"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        WAITING = "waiting", "Waiting"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey("AgentRun", on_delete=models.CASCADE, related_name="steps")
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.QUEUED
    )
    skill_name = models.CharField(max_length=128, blank=True)
    skill_version = models.CharField(max_length=64, blank=True)
    input_hash = models.CharField(max_length=64, blank=True)
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_step"
        ordering = ["run", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "sequence"], name="uq_agent_step_run_sequence"
            )
        ]
        indexes = [
            models.Index(fields=["kind", "status"], name="idx_agent_step_kind_status")
        ]


class ToolInvocation(models.Model):
    """Immutable audit record for one validated tool invocation."""

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    step = models.ForeignKey(
        "AgentStep", on_delete=models.PROTECT, related_name="tool_invocations"
    )
    tool_name = models.CharField(max_length=128)
    tool_version = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.RUNNING
    )
    parameters = models.JSONField(default=dict)
    parameter_hash = models.CharField(max_length=64)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=128, blank=True)
    idempotency_scope = models.CharField(max_length=128, blank=True)
    permission_scope = models.CharField(max_length=64)
    risk_level = models.CharField(max_length=16)
    has_side_effects = models.BooleanField(default=False)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tool_invocation"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "tool_name",
                    "tool_version",
                    "idempotency_scope",
                    "idempotency_key",
                ],
                condition=~Q(idempotency_key=""),
                name="uq_tool_invocation_idempotency",
            )
        ]
        indexes = [
            models.Index(fields=["step", "tool_name"], name="idx_tool_invocation_step"),
            models.Index(
                fields=["status", "-created_at"], name="idx_tool_invocation_status"
            ),
        ]
