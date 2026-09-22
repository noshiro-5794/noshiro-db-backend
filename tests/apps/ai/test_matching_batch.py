from unittest.mock import patch

import pytest

from apps.ai.models import AIProposal, AIRun
from apps.ai.services.matching_batch import ai_matching_batch_service
from apps.ai.tasks import evaluate_pending_candidates_task
from apps.index.models import Entity, MatchCandidate

pytestmark = pytest.mark.django_db(transaction=True)


def _candidate() -> MatchCandidate:
    left = Entity.objects.create(kind=Entity.Kind.WORK)
    right = Entity.objects.create(kind=Entity.Kind.WORK)
    first, second = sorted((left.pk, right.pk), key=lambda value: str(value))
    return MatchCandidate.objects.create(
        left_entity_id=first,
        right_entity_id=second,
        policy_version="title-similarity-v1",
        score="0.8000",
        runner_up_margin="0.1000",
        status=MatchCandidate.Status.PENDING,
        hard_conflicts=[],
    )


def test_dispatch_only_selects_candidates_without_proposals() -> None:
    pending = _candidate()
    already_evaluated = _candidate()
    run = AIRun.objects.create(
        use_case="entity_matching",
        provider="openai_compatible",
        model="fake",
        prompt_version="v1",
        input_hash="hash",
        status=AIRun.Status.SUCCEEDED,
    )
    AIProposal.objects.create(
        run=run,
        match_candidate=already_evaluated,
        proposal_type="entity_matching",
        payload={"decision": "abstain", "confidence": 0.1, "reason": "test"},
        confidence="0.1000",
    )

    with patch("apps.ai.tasks.evaluate_match_candidate_task.delay") as delay:
        result = ai_matching_batch_service.dispatch(limit=10)

    assert result["candidate_ids"] == [str(pending.pk)]
    delay.assert_called_once_with(str(pending.pk))


def test_task_uses_configured_batch_size() -> None:
    with patch.object(
        ai_matching_batch_service,
        "dispatch",
        return_value={"dispatched": 0, "candidate_ids": []},
    ) as dispatch:
        result = evaluate_pending_candidates_task.run(limit=7)

    dispatch.assert_called_once_with(limit=7)
    assert result == {"dispatched": 0, "candidate_ids": []}
