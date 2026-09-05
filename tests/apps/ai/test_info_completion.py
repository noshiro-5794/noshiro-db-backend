import hashlib
import json
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.ai.models import (
    AgentRun,
    AIClaim,
    ClaimEvidence,
    SourceArtifact,
    ToolInvocation,
)
from apps.ai.skills.info_completion import (
    InfoCompletionInput,
    info_completion_skill,
)
from apps.ai.tools.registry import ToolDefinition, ToolRegistry
from apps.ai.tools.web import WebSearchInput, WebSearchOutput
from apps.index.models import (
    Entity,
    EntityName,
    Observation,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
    ProviderRevision,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _fixture() -> tuple[Entity, Observation, AgentRun]:
    provider = Provider.objects.create(slug="bangumi", name="Bangumi")
    namespace = ProviderNamespace.objects.create(
        provider=provider, slug="subject", resource_type="subject"
    )
    record = ProviderRecord.objects.create(
        namespace=namespace, external_id="100", origin="api", status="active"
    )
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    ProviderRepresentation.objects.create(
        provider_record=record,
        entity=entity,
        mapping_kind=ProviderRepresentation.MappingKind.EXACT,
        method=ProviderRepresentation.Method.EXTERNAL_ID,
    )
    revision = ProviderRevision.objects.create(
        record=record,
        payload={"name": "Fate/stay night", "date": "2006-01-06"},
        payload_hash=_payload_hash({"name": "Fate/stay night"}),
    )
    ProviderRecord.objects.filter(pk=record.pk).update(latest_revision=revision)
    observation = Observation.objects.create(
        provider_record=record,
        origin=Observation.Origin.LEGACY,
        schema_name="bangumi_subject",
        schema_version="v1",
        normalized_data={
            "title": "Fate/stay night",
            "title_cn": "",
            "date": "2006-01-06",
            "description": "",
        },
        normalized_hash=_payload_hash({"title": "Fate/stay night"}),
    )
    run = AgentRun.objects.create(
        kind=AgentRun.Kind.ADMIN_SYNC,
        title="test enrich",
        idempotency_key="campaign-1",
        idempotency_scope="sync:test",
        metadata={"scopes": ["knowledge:read"]},
    )
    return entity, observation, run


def _input(entity: Entity) -> InfoCompletionInput:
    return InfoCompletionInput(
        entity_id=str(entity.pk),
        provider="bangumi",
        external_id="100",
        preferred_name="Fate/stay night",
        original_name="Fate/stay night",
        release_date="2006-01-06",
        missing_fields=["title:zh", "description:zh"],
        existing_names={},
    )


def _model_output(**proposal_overrides) -> dict:
    proposal = {
        "field": "title",
        "language": "zh",
        "script": "",
        "text": "命运之夜",
        "kind": "translated",
        "confidence": 0.9,
        "reason": "Official Chinese title on evidence.",
        "source": "model",
    }
    proposal.update(proposal_overrides)
    return {
        "strategy": "complete",
        "proposals": [proposal],
        "summary": "Completed one field.",
    }


def test_high_confidence_title_is_applied_when_enabled() -> None:
    entity, observation, run = _fixture()

    with patch(
        "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
        return_value=(_model_output(), {"input_tokens": 10, "output_tokens": 5}),
    ):
        summary = info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
            apply=True,
            min_confidence=0.8,
        )

    assert summary["claims"] == 1
    assert summary["applied"] == 1
    claim = AIClaim.objects.get()
    assert claim.claim_type == "info_completion"
    assert claim.status == AIClaim.Status.ACCEPTED
    assert float(claim.calibrated_confidence) == pytest.approx(0.81)
    assert ClaimEvidence.objects.filter(claim=claim, observation=observation).exists()
    name = EntityName.objects.get(entity=entity, language="zh")
    assert name.text == "命运之夜"
    assert name.is_machine_generated is True
    assert name.is_reviewed is False


def test_low_confidence_stays_proposed_without_applying() -> None:
    entity, observation, run = _fixture()

    with patch(
        "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
        return_value=(_model_output(confidence=0.6), {}),
    ):
        summary = info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
            apply=True,
            min_confidence=0.8,
        )

    assert summary["applied"] == 0
    assert AIClaim.objects.get().status == AIClaim.Status.PROPOSED
    assert EntityName.objects.count() == 0


def test_shadow_mode_never_applies() -> None:
    entity, observation, run = _fixture()

    with patch(
        "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
        return_value=(_model_output(), {}),
    ):
        summary = info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
            apply=False,
        )

    assert summary["claims"] == 1
    assert summary["applied"] == 0
    assert EntityName.objects.count() == 0


def test_description_proposals_are_claims_only() -> None:
    entity, observation, run = _fixture()
    output = {
        "strategy": "complete",
        "proposals": [
            {
                "field": "description",
                "language": "zh",
                "script": "",
                "text": "高中生卫宫士郎的圣杯战争故事。",
                "kind": "translated",
                "confidence": 0.95,
                "reason": "Summary from official site.",
                "source": "web",
            }
        ],
        "summary": "Completed description.",
    }

    with patch(
        "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
        return_value=(output, {}),
    ):
        info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
            apply=True,
            min_confidence=0.5,
        )

    assert AIClaim.objects.count() == 1
    assert entity.descriptions.count() == 0


def test_abstain_persists_no_claims() -> None:
    entity, observation, run = _fixture()

    with patch(
        "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
        return_value=(
            {"strategy": "abstain", "proposals": [], "summary": "No evidence."},
            {},
        ),
    ):
        summary = info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
        )

    assert summary["abstained"] == 1
    assert AIClaim.objects.count() == 0


def test_schema_mismatch_retries_then_succeeds() -> None:
    entity, observation, run = _fixture()
    malformed = {
        "title:zh": {
            "value": None,
            "confidence": 0.0,
            "reason": "Unable to determine the title.",
        }
    }

    with patch(
        "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
        side_effect=[(malformed, {}), (_model_output(), {})],
    ):
        summary = info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
            apply=False,
        )

    assert summary["claims"] == 1
    assert AIClaim.objects.count() == 1


def test_schema_mismatch_retry_failure_abstains_without_raising() -> None:
    entity, observation, run = _fixture()
    malformed = {
        "title:zh": {
            "value": None,
            "confidence": 0.0,
            "reason": "Unable to determine the title.",
        }
    }

    with patch(
        "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
        side_effect=[(malformed, {}), (malformed, {})],
    ):
        summary = info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
        )

    assert summary["abstained"] == 1
    assert summary["claims"] == 0
    assert AIClaim.objects.count() == 0


@override_settings(
    WEB_SEARCH_PROVIDER="tavily",
    WEB_SEARCH_API_KEY="test-key",
)
def test_web_evidence_raises_strength_and_persists_artifacts() -> None:
    entity, observation, run = _fixture()
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="web.search",
            description="test",
            input_model=WebSearchInput,
            output_model=WebSearchOutput,
            handler=lambda _value: WebSearchOutput(
                available=True,
                results=[
                    {
                        "title": "命运之夜 - 维基百科",
                        "url": "https://example.org/fate",
                        "content": "Fate/stay night 的中文译名是命运之夜。",
                        "score": 0.9,
                    }
                ],
            ),
            version="1.0.0",
            records_evidence=True,
        )
    )

    with (
        patch(
            "apps.ai.skills.info_completion.handler.create_default_tool_registry",
            return_value=registry,
        ),
        patch(
            "apps.ai.skills.info_completion.handler.ai_gateway.complete_json",
            return_value=(_model_output(source="web"), {}),
        ),
    ):
        summary = info_completion_skill.complete(
            _input(entity),
            target_entity=entity,
            agent_run=run,
            source_observation=observation,
            apply=True,
            min_confidence=0.85,
        )

    assert summary["applied"] == 1
    claim = AIClaim.objects.get()
    assert float(claim.evidence_strength) == pytest.approx(1.0)
    assert float(claim.calibrated_confidence) == pytest.approx(0.9)
    assert ToolInvocation.objects.filter(tool_name="web.search").count() == 1
    artifact = SourceArtifact.objects.get(kind=SourceArtifact.Kind.SEARCH_RESULT)
    assert artifact.source_url == "https://example.org/fate"
    assert ClaimEvidence.objects.filter(claim=claim, artifact=artifact).exists()


@override_settings(WEB_SEARCH_CACHE_DAYS=30)
def test_web_search_results_are_reused_within_cache_window() -> None:
    entity, _observation, _run = _fixture()
    registry = ToolRegistry()
    calls = {"n": 0}

    def fake_search(_value: WebSearchInput) -> WebSearchOutput:
        calls["n"] += 1
        return WebSearchOutput(
            available=True,
            results=[
                {
                    "title": "命运之夜",
                    "url": "https://example.org/fate",
                    "content": "Fate/stay night 的中文译名是命运之夜。",
                    "score": 0.9,
                }
            ],
        )

    registry.register(
        ToolDefinition(
            name="web.search",
            description="test",
            input_model=WebSearchInput,
            output_model=WebSearchOutput,
            handler=fake_search,
            version="1.0.0",
            records_evidence=True,
        )
    )

    def gather(run: AgentRun):
        with patch(
            "apps.ai.skills.info_completion.handler.create_default_tool_registry",
            return_value=registry,
        ):
            return info_completion_skill._gather_web_evidence(
                value=_input(entity), agent_run=run
            )

    run1 = AgentRun.objects.create(
        kind=AgentRun.Kind.ADMIN_SYNC,
        title="cache-1",
        idempotency_key="cache-1",
        idempotency_scope="cache-test",
    )
    run2 = AgentRun.objects.create(
        kind=AgentRun.Kind.ADMIN_SYNC,
        title="cache-2",
        idempotency_key="cache-2",
        idempotency_scope="cache-test",
    )

    first = gather(run1)
    second = gather(run2)

    assert len(first) == len(second) == 1
    assert first[0].pk == second[0].pk
    assert calls["n"] == 1
    assert ToolInvocation.objects.filter(tool_name="web.search").count() == 1
