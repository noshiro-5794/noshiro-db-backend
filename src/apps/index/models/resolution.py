import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .base import TimestampedModel


class ProviderRepresentation(TimestampedModel):
    class MappingKind(models.TextChoices):
        EXACT = "exact", "Exact"
        AGGREGATE = "aggregate", "Aggregate"
        PARTIAL = "partial", "Partial"
        VARIANT = "variant", "Variant"

    class Method(models.TextChoices):
        PROVIDER = "provider", "Provider"
        EXTERNAL_ID = "external_id", "Verified external ID"
        RESOLVER = "resolver", "Resolver"
        AI = "ai", "AI policy"
        MANUAL = "manual", "Manual"
        LEGACY = "legacy", "Legacy backfill"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider_record = models.ForeignKey(
        "ProviderRecord",
        on_delete=models.PROTECT,
        related_name="representations",
    )
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="provider_representations"
    )
    mapping_kind = models.CharField(max_length=16, choices=MappingKind.choices)
    method = models.CharField(max_length=16, choices=Method.choices)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    is_active = models.BooleanField(default=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "provider_representation"
        constraints = [
            models.UniqueConstraint(
                fields=["provider_record", "entity", "mapping_kind"],
                condition=Q(is_active=True),
                name="uq_active_provider_representation",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0, confidence__lte=1),
                name="ck_representation_confidence",
            ),
        ]
        indexes = [
            models.Index(
                fields=["provider_record", "is_active"],
                name="idx_representation_record",
            ),
            models.Index(
                fields=["entity", "is_active"], name="idx_representation_entity"
            ),
        ]


class MatchCandidate(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        ABSTAINED = "abstained", "Abstained"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    left_entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="left_match_candidates"
    )
    right_entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="right_match_candidates"
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    runner_up_margin = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    policy_version = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    hard_conflicts = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "match_candidate"
        constraints = [
            models.UniqueConstraint(
                fields=["left_entity", "right_entity", "policy_version"],
                name="uq_match_candidate_policy",
            ),
            models.CheckConstraint(
                condition=~Q(left_entity=models.F("right_entity")),
                name="ck_match_candidate_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-score"], name="idx_match_status_score")
        ]


class MatchEvidence(TimestampedModel):
    candidate = models.ForeignKey(
        "MatchCandidate", on_delete=models.CASCADE, related_name="evidence"
    )
    evidence_type = models.CharField(max_length=64)
    value = models.JSONField()
    weight = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    observation = models.ForeignKey(
        "Observation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="match_evidence",
    )

    class Meta:
        db_table = "match_evidence"
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "evidence_type", "observation"],
                name="uq_match_evidence_source",
                nulls_distinct=False,
            )
        ]


class MatchDecision(TimestampedModel):
    class Outcome(models.TextChoices):
        BIND = "bind", "Bind"
        REJECT = "reject", "Reject"
        ABSTAIN = "abstain", "Abstain"

    candidate = models.ForeignKey(
        "MatchCandidate", on_delete=models.CASCADE, related_name="decisions"
    )
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    decided_by = models.CharField(max_length=32)
    policy_version = models.CharField(max_length=64)
    reason = models.TextField(blank=True)
    decision_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "match_decision"
        indexes = [
            models.Index(
                fields=["candidate", "-created_at"], name="idx_match_decision_latest"
            )
        ]


class ResolutionDecision(TimestampedModel):
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, related_name="resolution_decisions"
    )
    predicate = models.ForeignKey(
        "Predicate", on_delete=models.PROTECT, related_name="resolution_decisions"
    )
    language = models.CharField(max_length=35, blank=True)
    selected_fact = models.ForeignKey(
        "Fact",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="selection_decisions",
    )
    policy_version = models.CharField(max_length=64)
    reason = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "resolution_decision"
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "predicate", "language"],
                condition=Q(is_active=True),
                name="uq_active_resolution_decision",
            )
        ]


class MergeEvent(TimestampedModel):
    class Method(models.TextChoices):
        RULE = "rule", "Rule"
        AI_POLICY = "ai_policy", "AI policy"
        MANUAL = "manual", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_entity = models.ForeignKey(
        "Entity", on_delete=models.PROTECT, related_name="merge_source_events"
    )
    target_entity = models.ForeignKey(
        "Entity", on_delete=models.PROTECT, related_name="merge_target_events"
    )
    method = models.CharField(max_length=16, choices=Method.choices)
    reason = models.TextField()
    snapshot = models.JSONField(default=dict)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "entity_merge_event"
        constraints = [
            models.CheckConstraint(
                condition=~Q(source_entity=models.F("target_entity")),
                name="ck_merge_event_not_self",
            )
        ]


class EntityRedirect(TimestampedModel):
    source_entity = models.ForeignKey(
        "Entity",
        on_delete=models.CASCADE,
        related_name="outgoing_redirects",
    )
    target_entity = models.ForeignKey(
        "Entity", on_delete=models.PROTECT, related_name="incoming_redirects"
    )
    merge_event = models.OneToOneField(
        "MergeEvent", on_delete=models.PROTECT, related_name="redirect"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "entity_redirect"
        constraints = [
            models.CheckConstraint(
                condition=~Q(source_entity=models.F("target_entity")),
                name="ck_entity_redirect_not_self",
            ),
            models.UniqueConstraint(
                fields=["source_entity"],
                condition=Q(is_active=True),
                name="uq_active_entity_redirect_source",
            ),
        ]


class SplitEvent(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merge_event = models.ForeignKey(
        "MergeEvent", on_delete=models.PROTECT, related_name="split_events"
    )
    reason = models.TextField()
    restored_snapshot = models.JSONField(default=dict)
    performed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "entity_split_event"
