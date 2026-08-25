from unittest.mock import patch

import pytest

from apps.ai.tasks import (
    classify_entity_task,
    evaluate_match_candidate_task,
    extract_observation_evidence_task,
)


@pytest.mark.django_db(transaction=True)
class TestEvaluateMatchCandidateTask:
    def test_returns_proposal_id(self) -> None:
        with patch(
            "apps.ai.tasks.ai_matching_service.evaluate"
        ) as mock_evaluate:
            mock_evaluate.return_value.id = "proposal-uuid"
            result = evaluate_match_candidate_task("candidate-uuid")
            assert result == "proposal-uuid"
            mock_evaluate.assert_called_once_with(candidate_id="candidate-uuid")


@pytest.mark.django_db(transaction=True)
class TestClassifyEntityTask:
    def test_returns_proposal_id(self) -> None:
        with patch(
            "apps.ai.tasks.ai_knowledge_proposal_service.classify_entity"
        ) as mock_classify:
            mock_classify.return_value.id = "proposal-uuid"
            result = classify_entity_task("entity-uuid")
            assert result == "proposal-uuid"
            mock_classify.assert_called_once_with(entity_id="entity-uuid")


@pytest.mark.django_db(transaction=True)
class TestExtractObservationEvidenceTask:
    def test_returns_proposal_id(self) -> None:
        with patch(
            "apps.ai.tasks.ai_knowledge_proposal_service.extract_evidence"
        ) as mock_extract:
            mock_extract.return_value.id = "proposal-uuid"
            result = extract_observation_evidence_task("obs-uuid", "entity-uuid")
            assert result == "proposal-uuid"
            mock_extract.assert_called_once_with(
                observation_id="obs-uuid", entity_id="entity-uuid"
            )
