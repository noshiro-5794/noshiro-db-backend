from unittest.mock import patch

import pytest

from apps.ai.models import AIProposal, AIRun
from apps.ai.services import (
    AIInputNotAllowed,
    InvalidAIProposal,
    ai_knowledge_proposal_service,
)
from apps.index.models import (
    CurrentObservation,
    Entity,
    Fact,
    Observation,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
    Work,
)
from integrations.ai import AIProviderError

pytestmark = pytest.mark.django_db(transaction=True)


def _work(*, visibility: str = Entity.Visibility.PUBLIC) -> tuple[Entity, Work]:
    entity = Entity.objects.create(kind=Entity.Kind.WORK, visibility=visibility)
    return entity, Work.objects.create(entity=entity)


def _observation(
    *,
    entity: Entity,
    policy: str = Provider.UsagePolicy.ALLOWED,
    current: bool = True,
) -> Observation:
    provider = Provider.objects.create(
        slug=f"provider-{Provider.objects.count()}",
        name="Fixture provider",
        ai_usage_policy=policy,
    )
    namespace = ProviderNamespace.objects.create(
        provider=provider,
        slug="works",
        resource_type=ProviderNamespace.ResourceType.SUBJECT,
    )
    record = ProviderRecord.objects.create(
        namespace=namespace,
        external_id="work-1",
        origin=ProviderRecord.Origin.API,
    )
    observation = Observation.objects.create(
        provider_record=record,
        origin=Observation.Origin.LEGACY,
        schema_name="fixture.work",
        schema_version="1",
        normalized_data={"title": "Fixture", "developer": "Studio"},
        normalized_hash="a" * 64,
    )
    ProviderRepresentation.objects.create(
        provider_record=record,
        entity=entity,
        mapping_kind=ProviderRepresentation.MappingKind.EXACT,
        method=ProviderRepresentation.Method.PROVIDER,
    )
    if current:
        CurrentObservation.objects.create(
            provider_record=record,
            mapper="fixture",
            schema_name=observation.schema_name,
            observation=observation,
        )
    return observation


def test_classification_creates_only_a_shadow_proposal() -> None:
    entity, work = _work()

    with patch(
        "apps.ai.services.knowledge.ai_gateway.complete_json",
        return_value=(
            {
                "work_type": Work.WorkType.GALGAME,
                "confidence": "0.98",
                "reason": "The supplied metadata describes a galgame.",
            },
            {"input_tokens": 12, "output_tokens": 6},
        ),
    ):
        proposal = ai_knowledge_proposal_service.classify_entity(entity_id=entity.id)

    work.refresh_from_db()
    assert work.work_type == Work.WorkType.UNCLASSIFIED
    assert proposal.status == AIProposal.Status.PENDING
    assert proposal.target_entity == entity
    assert proposal.match_candidate is None
    assert proposal.run.status == AIRun.Status.SUCCEEDED
    assert proposal.payload["work_type"] == Work.WorkType.GALGAME
    assert Fact.objects.count() == 0


@pytest.mark.parametrize(
    "policy",
    [
        Provider.UsagePolicy.UNKNOWN,
        Provider.UsagePolicy.RESTRICTED,
        Provider.UsagePolicy.FORBIDDEN,
    ],
)
def test_classification_abstains_when_a_provider_does_not_allow_ai(policy: str) -> None:
    entity, _ = _work()
    _observation(entity=entity, policy=policy)

    with patch("apps.ai.services.knowledge.ai_gateway.complete_json") as complete_json:
        proposal = ai_knowledge_proposal_service.classify_entity(entity_id=entity.id)

    complete_json.assert_not_called()
    assert proposal.status == AIProposal.Status.ABSTAINED
    assert proposal.run.status == AIRun.Status.ABSTAINED
    assert proposal.run.provider == "policy_gate"


def test_restricted_entity_never_reaches_the_ai_gateway() -> None:
    entity, _ = _work(visibility=Entity.Visibility.RESTRICTED)

    with patch("apps.ai.services.knowledge.ai_gateway.complete_json") as complete_json:
        proposal = ai_knowledge_proposal_service.classify_entity(entity_id=entity.id)

    complete_json.assert_not_called()
    assert proposal.status == AIProposal.Status.ABSTAINED
    assert "Restricted entities" in proposal.policy_reason


def test_allowed_provider_creates_validated_evidence_proposal_only() -> None:
    entity, _ = _work()
    observation = _observation(entity=entity)
    output = {
        "claims": [
            {
                "predicate": "developer",
                "value": "Studio",
                "value_type": "string",
                "language": "en",
                "spoiler_level": 0,
                "safety": "safe",
                "json_pointer": "/developer",
                "confidence": "0.99",
            }
        ]
    }

    with patch(
        "apps.ai.services.knowledge.ai_gateway.complete_json",
        return_value=(output, {}),
    ):
        proposal = ai_knowledge_proposal_service.extract_evidence(
            observation_id=observation.id,
            entity_id=entity.id,
        )

    assert proposal.status == AIProposal.Status.PENDING
    assert proposal.source_observation == observation
    assert proposal.target_entity == entity
    assert proposal.payload["claims"][0]["confidence"] == "0.99"
    assert Fact.objects.count() == 0


@pytest.mark.parametrize(
    "policy",
    [
        Provider.UsagePolicy.UNKNOWN,
        Provider.UsagePolicy.RESTRICTED,
        Provider.UsagePolicy.FORBIDDEN,
    ],
)
def test_evidence_extraction_abstains_for_disallowed_provider(policy: str) -> None:
    entity, _ = _work()
    observation = _observation(entity=entity, policy=policy)

    with patch("apps.ai.services.knowledge.ai_gateway.complete_json") as complete_json:
        proposal = ai_knowledge_proposal_service.extract_evidence(
            observation_id=observation.id,
            entity_id=entity.id,
        )

    complete_json.assert_not_called()
    assert proposal.status == AIProposal.Status.ABSTAINED
    assert Fact.objects.count() == 0


def test_observation_must_be_current_and_bound_to_the_target_entity() -> None:
    entity, _ = _work()
    other_entity, _ = _work()
    observation = _observation(entity=entity, current=False)

    with pytest.raises(AIInputNotAllowed, match="active representation"):
        ai_knowledge_proposal_service.extract_evidence(
            observation_id=observation.id,
            entity_id=other_entity.id,
        )

    with pytest.raises(AIInputNotAllowed, match="current observation"):
        ai_knowledge_proposal_service.extract_evidence(
            observation_id=observation.id,
            entity_id=entity.id,
        )

    assert AIRun.objects.count() == 0


@pytest.mark.parametrize(
    ("provider_result", "error_type", "message"),
    [
        (({"work_type": "invalid"}, {}), InvalidAIProposal, "work_type"),
        (AIProviderError("provider unavailable"), AIProviderError, "unavailable"),
    ],
)
def test_classification_failure_preserves_failed_run(
    provider_result,
    error_type,
    message: str,
) -> None:
    entity, _ = _work()
    patch_kwargs = (
        {"side_effect": provider_result}
        if isinstance(provider_result, Exception)
        else {"return_value": provider_result}
    )

    with (
        patch(
            "apps.ai.services.knowledge.ai_gateway.complete_json",
            **patch_kwargs,
        ),
        pytest.raises(error_type, match=message),
    ):
        ai_knowledge_proposal_service.classify_entity(entity_id=entity.id)

    run = AIRun.objects.get()
    assert run.status == AIRun.Status.FAILED
    assert run.finished_at is not None
    assert AIProposal.objects.count() == 0
