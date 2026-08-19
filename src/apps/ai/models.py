import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AIRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        ABSTAINED = "abstained", "Abstained"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    use_case = models.CharField(max_length=64)
    provider = models.CharField(max_length=64)
    model = models.CharField(max_length=256)
    prompt_version = models.CharField(max_length=64)
    input_hash = models.CharField(max_length=64)
    input_metadata = models.JSONField(default=dict, blank=True)
    output = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ai_run"
        indexes = [
            models.Index(
                fields=["use_case", "-created_at"], name="idx_ai_run_use_case"
            ),
            models.Index(fields=["status", "created_at"], name="idx_ai_run_status"),
            models.Index(fields=["input_hash"], name="idx_ai_run_input_hash"),
        ]


class AIPolicy(models.Model):
    use_case = models.CharField(max_length=64, unique=True)
    policy_version = models.CharField(max_length=64)
    shadow_mode = models.BooleanField(default=True)
    minimum_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default="0.9950",
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    minimum_margin = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default="0.0500",
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    minimum_evidence_types = models.PositiveSmallIntegerField(default=2)
    required_evaluation_precision = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default="0.9990",
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_policy"


class AIProposal(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        ABSTAINED = "abstained", "Abstained"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey("AIRun", on_delete=models.PROTECT, related_name="proposals")
    match_candidate = models.ForeignKey(
        "index.MatchCandidate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ai_proposals",
    )
    target_entity = models.ForeignKey(
        "index.Entity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ai_proposals",
    )
    source_observation = models.ForeignKey(
        "index.Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ai_proposals",
    )
    proposal_type = models.CharField(max_length=64)
    payload = models.JSONField()
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    policy_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ai_proposal"
        indexes = [
            models.Index(
                fields=["proposal_type", "status"], name="idx_ai_proposal_status"
            )
        ]


class AIEvaluationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    use_case = models.CharField(max_length=64)
    policy_version = models.CharField(max_length=64)
    dataset_version = models.CharField(max_length=64)
    sample_count = models.PositiveIntegerField()
    precision = models.DecimalField(max_digits=5, decimal_places=4)
    recall = models.DecimalField(max_digits=5, decimal_places=4)
    metrics = models.JSONField(default=dict, blank=True)
    passed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_evaluation_run"
        indexes = [
            models.Index(
                fields=["use_case", "policy_version", "-created_at"],
                name="idx_ai_evaluation_latest",
            )
        ]
