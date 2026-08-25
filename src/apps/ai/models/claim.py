import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class AIClaim(models.Model):
    """Field-level candidate conclusion produced by a versioned skill."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    step = models.ForeignKey(
        "AgentStep", on_delete=models.PROTECT, related_name="claims"
    )
    proposal = models.ForeignKey(
        "AIProposal",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="claims",
    )
    target_entity = models.ForeignKey(
        "index.Entity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ai_claims",
    )
    claim_type = models.CharField(max_length=64)
    predicate_slug = models.CharField(max_length=128, blank=True)
    proposed_value = models.JSONField()
    model_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    evidence_strength = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    calibrated_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PROPOSED
    )
    policy_decision = models.CharField(max_length=64, blank=True)
    policy_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ai_claim"
        indexes = [
            models.Index(
                fields=["target_entity", "claim_type"], name="idx_ai_claim_target_type"
            ),
            models.Index(fields=["status", "-created_at"], name="idx_ai_claim_status"),
        ]


class ClaimEvidence(models.Model):
    """Exact observation or artifact fragment supporting one claim."""

    claim = models.ForeignKey(
        "AIClaim", on_delete=models.CASCADE, related_name="evidence_links"
    )
    observation = models.ForeignKey(
        "index.Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="claim_evidence_links",
    )
    artifact = models.ForeignKey(
        "SourceArtifact",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="claim_evidence_links",
    )
    locator = models.CharField(max_length=512)
    excerpt = models.TextField(blank=True)
    excerpt_hash = models.CharField(max_length=64, blank=True)
    relevance = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    class Meta:
        db_table = "claim_evidence"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(observation__isnull=False, artifact__isnull=True)
                    | Q(observation__isnull=True, artifact__isnull=False)
                ),
                name="ck_claim_evidence_one_source",
            ),
            models.UniqueConstraint(
                fields=["claim", "observation", "artifact", "locator"],
                name="uq_claim_evidence_source_locator",
                nulls_distinct=False,
            ),
        ]


class ApprovalRequest(models.Model):
    """Admin review or one-time user confirmation for a proposed change."""

    class Kind(models.TextChoices):
        ADMIN_REVIEW = "admin_review", "Admin review"
        USER_CONFIRM = "user_confirm", "User confirmation"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    run = models.ForeignKey(
        "AgentRun", on_delete=models.PROTECT, related_name="approval_requests"
    )
    step = models.ForeignKey(
        "AgentStep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_requests",
    )
    requester = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approval_requests",
    )
    reviewer = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_approvals",
    )
    summary = models.TextField()
    diff = models.JSONField(default=dict)
    risk_level = models.CharField(max_length=16)
    idempotency_key = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "approval_request"
        indexes = [
            models.Index(
                fields=["status", "kind"], name="idx_approval_req_status_kind"
            ),
            models.Index(
                fields=["reviewer", "status"], name="idx_approval_req_reviewer"
            ),
        ]
