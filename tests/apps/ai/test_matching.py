from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.ai.models import AIEvaluationRun, AIPolicy, AIProposal, AIRun
from apps.ai.services import InvalidAIProposal, ai_matching_service
from apps.index.models import (
    Entity,
    MatchCandidate,
    MatchDecision,
    MatchEvidence,
)
from integrations.ai import AIProviderError

pytestmark = pytest.mark.django_db(transaction=True)


def _candidate(
    *,
    score: str = "0.9990",
    margin: str = "0.1000",
    hard_conflicts: list | None = None,
    right_kind: str = Entity.Kind.WORK,
) -> MatchCandidate:
    left = Entity.objects.create(kind=Entity.Kind.WORK)
    right = Entity.objects.create(kind=right_kind)
    candidate = MatchCandidate.objects.create(
        left_entity=left,
        right_entity=right,
        score=score,
        runner_up_margin=margin,
        policy_version="match-v1",
        hard_conflicts=hard_conflicts or [],
    )
    MatchEvidence.objects.create(
        candidate=candidate,
        evidence_type="official_external_id",
        value={"id": "same"},
        weight="1.0",
    )
    MatchEvidence.objects.create(
        candidate=candidate,
        evidence_type="release_and_creator",
        value={"date": "2026", "creator": "same"},
        weight="1.0",
    )
    return candidate


def _provider_result(
    *, decision: str = "bind", confidence: str = "0.9990"
) -> tuple[dict, dict]:
    return (
        {
            "decision": decision,
            "confidence": confidence,
            "reason": "Evidence agrees.",
        },
        {"input_tokens": 10, "output_tokens": 5, "cost": "0.001"},
    )


def test_provider_failure_keeps_failed_run_audit() -> None:
    candidate = _candidate()

    with (
        patch(
            "apps.ai.services.matching.ai_gateway.complete_json",
            side_effect=AIProviderError("provider unavailable"),
        ),
        pytest.raises(AIProviderError, match="provider unavailable"),
    ):
        ai_matching_service.evaluate(candidate_id=candidate.id)

    run = AIRun.objects.get()
    assert run.status == AIRun.Status.FAILED
    assert "provider unavailable" in run.error
    assert run.finished_at is not None
    assert AIProposal.objects.count() == 0


def test_invalid_structured_output_keeps_failed_run_audit() -> None:
    candidate = _candidate()

    with (
        patch(
            "apps.ai.services.matching.ai_gateway.complete_json",
            return_value=({"decision": "maybe", "confidence": 2}, {}),
        ),
        pytest.raises(InvalidAIProposal, match="decision"),
    ):
        ai_matching_service.evaluate(candidate_id=candidate.id)

    assert AIRun.objects.get().status == AIRun.Status.FAILED
    assert MatchDecision.objects.count() == 0


def test_shadow_run_persists_proposal_without_deciding_candidate() -> None:
    candidate = _candidate()

    with patch(
        "apps.ai.services.matching.ai_gateway.complete_json",
        return_value=_provider_result(),
    ):
        proposal = ai_matching_service.evaluate(candidate_id=candidate.id)

    candidate.refresh_from_db()
    assert proposal.status == AIProposal.Status.PENDING
    assert "Shadow proposal only" in proposal.policy_reason
    assert proposal.decided_at is None
    assert candidate.status == MatchCandidate.Status.PENDING
    assert MatchDecision.objects.count() == 0
    run = proposal.run
    assert run.status == AIRun.Status.SUCCEEDED
    assert run.input_tokens == 10
    assert run.output_tokens == 5
    assert run.cost == Decimal("0.001")


def test_production_ready_policy_accepts_only_fully_gated_bind() -> None:
    candidate = _candidate()
    policy = AIPolicy.objects.create(
        use_case=ai_matching_service.USE_CASE,
        policy_version=candidate.policy_version,
        shadow_mode=False,
    )
    AIEvaluationRun.objects.create(
        use_case=policy.use_case,
        policy_version=policy.policy_version,
        dataset_version="verified-v1",
        sample_count=1000,
        precision="0.9990",
        recall="0.9000",
        passed=True,
    )

    with patch(
        "apps.ai.services.matching.ai_gateway.complete_json",
        return_value=_provider_result(),
    ):
        proposal = ai_matching_service.evaluate(candidate_id=candidate.id)

    candidate.refresh_from_db()
    assert proposal.status == AIProposal.Status.ACCEPTED
    assert candidate.status == MatchCandidate.Status.ACCEPTED
    decision = MatchDecision.objects.get(candidate=candidate)
    assert decision.outcome == MatchDecision.Outcome.BIND
    assert decision.decided_by == "ai_policy"


@pytest.mark.parametrize(
    ("candidate_kwargs", "confidence"),
    [
        ({"score": "0.9900"}, "0.9990"),
        ({"margin": "0.0100"}, "0.9990"),
        ({"hard_conflicts": ["release_date"]}, "0.9990"),
        ({"right_kind": Entity.Kind.CHARACTER}, "0.9990"),
        ({}, "0.9000"),
    ],
)
def test_production_policy_abstains_when_any_bind_gate_fails(
    candidate_kwargs: dict,
    confidence: str,
) -> None:
    candidate = _candidate(**candidate_kwargs)
    policy = AIPolicy.objects.create(
        use_case=ai_matching_service.USE_CASE,
        policy_version=candidate.policy_version,
        shadow_mode=False,
    )
    AIEvaluationRun.objects.create(
        use_case=policy.use_case,
        policy_version=policy.policy_version,
        dataset_version="verified-v1",
        sample_count=1000,
        precision="0.9990",
        recall="0.9000",
        passed=True,
    )

    with patch(
        "apps.ai.services.matching.ai_gateway.complete_json",
        return_value=_provider_result(confidence=confidence),
    ):
        proposal = ai_matching_service.evaluate(candidate_id=candidate.id)

    candidate.refresh_from_db()
    assert proposal.status == AIProposal.Status.ABSTAINED
    assert candidate.status == MatchCandidate.Status.ABSTAINED
    assert MatchDecision.objects.get(candidate=candidate).outcome == "abstain"
