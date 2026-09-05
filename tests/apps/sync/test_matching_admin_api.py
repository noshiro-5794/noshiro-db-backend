from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.ai.models import AIProposal, AIRun
from apps.index.models import Entity, MatchCandidate, MatchEvidence

pytestmark = pytest.mark.django_db(transaction=True)


def _candidate_with_proposal() -> tuple[MatchCandidate, AIProposal]:
    left = Entity.objects.create(kind=Entity.Kind.WORK)
    right = Entity.objects.create(kind=Entity.Kind.WORK)
    candidate = MatchCandidate.objects.create(
        left_entity=left,
        right_entity=right,
        policy_version="title-similarity-v1",
        score=Decimal("0.9000"),
        runner_up_margin=Decimal("0.1000"),
        status=MatchCandidate.Status.PENDING,
        hard_conflicts=[],
    )
    MatchEvidence.objects.create(
        candidate=candidate,
        evidence_type="title_similarity",
        value={"similarity": 0.9},
        weight=Decimal("0.9000"),
    )
    run = AIRun.objects.create(
        use_case="entity_matching",
        provider="test",
        model="test-model",
        prompt_version="test-v1",
        input_hash="a" * 64,
        status=AIRun.Status.SUCCEEDED,
    )
    proposal = AIProposal.objects.create(
        run=run,
        match_candidate=candidate,
        proposal_type="entity_matching",
        payload={
            "decision": "bind",
            "confidence": 0.9,
            "reason": "same title",
        },
        confidence=Decimal("0.9000"),
        status=AIProposal.Status.PENDING,
    )
    return candidate, proposal


def _admin_client() -> APIClient:
    user = get_user_model().objects.create_user(
        "admin@example.test",
        "x",
        is_staff=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_list_candidates_exposes_latest_proposal() -> None:
    candidate, proposal = _candidate_with_proposal()
    client = _admin_client()

    response = client.get("/api/v1/operations/matching/candidates/")

    assert response.status_code == 200
    results = response.data["results"]
    assert len(results) == 1
    row = results[0]
    assert str(row["id"]) == str(candidate.pk)
    assert row["evidence_count"] == 1
    assert row["latest_proposal"]["decision"] == "bind"
    assert row["latest_proposal"]["status"] == "pending"
    assert str(row["latest_proposal"]["id"]) == str(proposal.pk)


def test_admin_reject_decides_candidate_and_proposal() -> None:
    candidate, proposal = _candidate_with_proposal()
    client = _admin_client()

    response = client.post(
        f"/api/v1/operations/matching/candidates/{candidate.pk}/decide/",
        {"outcome": "reject", "reason": "different works"},
        format="json",
    )

    assert response.status_code == 200
    candidate.refresh_from_db()
    proposal.refresh_from_db()
    assert candidate.status == MatchCandidate.Status.REJECTED
    assert proposal.status == AIProposal.Status.REJECTED
    assert proposal.decided_at is not None


def test_second_decision_is_conflict() -> None:
    candidate, _proposal = _candidate_with_proposal()
    client = _admin_client()

    first = client.post(
        f"/api/v1/operations/matching/candidates/{candidate.pk}/decide/",
        {"outcome": "reject", "reason": "not the same work"},
        format="json",
    )
    second = client.post(
        f"/api/v1/operations/matching/candidates/{candidate.pk}/decide/",
        {"outcome": "bind", "reason": "retry"},
        format="json",
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_unknown_candidate_returns_not_found() -> None:
    client = _admin_client()

    response = client.post(
        "/api/v1/operations/matching/candidates/"
        "00000000-0000-0000-0000-000000000000/decide/",
        {"outcome": "bind", "reason": "should 404"},
        format="json",
    )

    assert response.status_code == 404
