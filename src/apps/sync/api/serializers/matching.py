from typing import Any

from rest_framework import serializers

from apps.ai.models import AIProposal
from apps.index.models import MatchCandidate


class LatestProposalSerializer(serializers.ModelSerializer):
    decision = serializers.SerializerMethodField()
    confidence = serializers.SerializerMethodField()

    class Meta:
        model = AIProposal
        fields = (
            "id",
            "status",
            "decision",
            "confidence",
            "policy_reason",
            "created_at",
            "decided_at",
        )

    def get_decision(self, proposal: AIProposal) -> str:
        return str((proposal.payload or {}).get("decision") or "")

    def get_confidence(self, proposal: AIProposal) -> float:
        try:
            return float(proposal.confidence)
        except (TypeError, ValueError):
            return 0.0


class MatchCandidateSerializer(serializers.ModelSerializer):
    left_entity = serializers.UUIDField(source="left_entity_id", read_only=True)
    right_entity = serializers.UUIDField(source="right_entity_id", read_only=True)
    evidence_count = serializers.SerializerMethodField()
    latest_proposal = serializers.SerializerMethodField()

    class Meta:
        model = MatchCandidate
        fields = (
            "id",
            "left_entity",
            "right_entity",
            "policy_version",
            "score",
            "runner_up_margin",
            "status",
            "hard_conflicts",
            "evidence_count",
            "latest_proposal",
            "created_at",
            "updated_at",
        )

    def get_evidence_count(self, candidate: MatchCandidate) -> int:
        return candidate.evidence.count()

    def get_latest_proposal(self, candidate: MatchCandidate) -> dict[str, Any] | None:
        proposal = (
            AIProposal.objects.filter(match_candidate=candidate)
            .select_related("run")
            .order_by("-created_at")
            .first()
        )
        return LatestProposalSerializer(proposal).data if proposal else None
