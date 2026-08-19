import uuid
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AIProposal, AIRun
from apps.ai.services.matching import AIMatchingService
from apps.index.models import MatchCandidate


class AIProposalService:
    @transaction.atomic
    def submit(
        self,
        *,
        candidate_id: uuid.UUID,
        decision: str,
        confidence: Decimal,
        reason: str,
        prompt_version: str,
        input_metadata: dict[str, Any] | None = None,
    ) -> AIProposal:
        candidate = MatchCandidate.objects.select_for_update().get(pk=candidate_id)
        output = AIMatchingService._validate_output(
            {
                "decision": decision,
                "confidence": str(confidence),
                "reason": reason,
            }
        )
        now = timezone.now()
        payload = {
            "candidate_id": str(candidate.id),
            "decision": output["decision"],
            "confidence": output["confidence"],
            "reason": output["reason"],
        }
        run = AIRun.objects.create(
            use_case=AIMatchingService.USE_CASE,
            provider="internal_mcp",
            model="mcp_client",
            prompt_version=prompt_version[:64],
            input_hash=AIMatchingService._input_hash(payload),
            input_metadata={
                "candidate_id": str(candidate.id),
                **(input_metadata or {}),
            },
            output=output,
            status=AIRun.Status.SUCCEEDED,
            started_at=now,
            finished_at=now,
        )
        return AIProposal.objects.create(
            run=run,
            match_candidate=candidate,
            proposal_type=AIMatchingService.USE_CASE,
            payload=output,
            confidence=Decimal(output["confidence"]),
            policy_reason=(
                "Submitted through internal MCP for deterministic policy evaluation; "
                "no canonical write was performed."
            ),
        )


ai_proposal_service = AIProposalService()
