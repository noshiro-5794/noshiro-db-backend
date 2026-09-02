from django.utils import timezone
from rest_framework import serializers

from apps.ai.models import AIClaim, ClaimEvidence
from apps.sync.models import SyncCampaign, SyncWorkItem


class SyncCampaignCreateSerializer(serializers.Serializer):
    provider = serializers.CharField()
    campaign_type = serializers.ChoiceField(
        choices=("full", "incremental"), default="full"
    )
    ai_mode = serializers.ChoiceField(
        choices=SyncCampaign.AIMode.choices, default=SyncCampaign.AIMode.SHADOW
    )
    parameters = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, max_length=128
    )

    def validate_provider(self, value: str) -> str:
        if value not in {"bangumi", "vndb", "anilist"}:
            raise serializers.ValidationError("Unsupported sync provider.")
        return value


class SyncCampaignSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()

    class Meta:
        model = SyncCampaign
        fields = (
            "id",
            "provider_slug",
            "campaign_type",
            "status",
            "ai_mode",
            "parameters",
            "total_items",
            "processed_items",
            "synced_items",
            "skipped_items",
            "failed_items",
            "quality_report",
            "cost",
            "error",
            "heartbeat_at",
            "next_run_at",
            "created_at",
            "started_at",
            "finished_at",
            "updated_at",
            "progress",
        )

    def get_progress(self, campaign: SyncCampaign) -> dict[str, int | float | None]:
        elapsed = (
            (timezone.now() - campaign.started_at).total_seconds()
            if campaign.started_at
            else 0
        )
        throughput = campaign.processed_items / elapsed if elapsed > 0 else None
        remaining = max(0, campaign.total_items - campaign.processed_items)
        return {
            "percent": round(campaign.processed_items / campaign.total_items * 100, 2)
            if campaign.total_items
            else None,
            "queued": campaign.work_items.filter(
                status=SyncWorkItem.Status.QUEUED
            ).count(),
            "running": campaign.work_items.filter(
                status=SyncWorkItem.Status.RUNNING
            ).count(),
            "succeeded": campaign.work_items.filter(
                status=SyncWorkItem.Status.SUCCEEDED
            ).count(),
            "failed": campaign.work_items.filter(
                status=SyncWorkItem.Status.FAILED
            ).count(),
            "retry_waiting": campaign.work_items.filter(
                next_retry_at__isnull=False
            ).count(),
            "throughput_items_per_second": round(throughput, 4)
            if throughput is not None
            else None,
            "eta_seconds": round(remaining / throughput)
            if throughput and throughput > 0
            else None,
        }


class SyncWorkItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncWorkItem
        fields = (
            "id",
            "shard",
            "cursor",
            "status",
            "provider_record",
            "result",
            "error",
            "attempt",
            "next_retry_at",
            "last_error_code",
            "ai_processed_at",
            "ai_enriched_at",
            "started_at",
            "finished_at",
            "updated_at",
        )


class ClaimEvidenceSerializer(serializers.ModelSerializer):
    source_url = serializers.CharField(source="artifact.source_url", read_only=True)
    observation = serializers.UUIDField(
        source="observation_id", read_only=True, allow_null=True
    )

    class Meta:
        model = ClaimEvidence
        fields = (
            "locator",
            "excerpt",
            "excerpt_hash",
            "relevance",
            "source_url",
            "observation",
        )


class AIClaimSerializer(serializers.ModelSerializer):
    evidence = ClaimEvidenceSerializer(
        source="evidence_links", many=True, read_only=True
    )

    class Meta:
        model = AIClaim
        fields = (
            "id",
            "claim_type",
            "predicate_slug",
            "proposed_value",
            "model_confidence",
            "evidence_strength",
            "calibrated_confidence",
            "status",
            "policy_decision",
            "policy_reason",
            "created_at",
            "decided_at",
            "evidence",
        )
