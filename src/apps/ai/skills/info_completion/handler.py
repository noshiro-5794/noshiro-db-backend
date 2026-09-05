"""Evidence-first enrichment of missing multilingual entity fields."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from django.utils import timezone

from apps.ai.models import (
    AgentRun,
    AgentStep,
    AIClaim,
    AIRun,
    ClaimEvidence,
    SourceArtifact,
    ToolInvocation,
)
from apps.ai.services.common import (
    optional_non_negative_decimal,
    optional_non_negative_int,
)
from apps.ai.skills.registry import SkillDefinition, skill_registry
from apps.ai.tools.evidence import capture_artifact
from apps.ai.tools.registry import create_default_tool_registry
from apps.index.models import Entity, EntityName, Observation
from integrations.ai.gateway import ai_gateway

from .schemas import FieldProposal, InfoCompletionInput, InfoCompletionOutput

SKILL_NAME = "info_completion"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "info-completion-v1"
USE_CASE = "info_completion"
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You complete missing multilingual metadata for an ACG entity.
Use only the supplied entity facts and web evidence. Never invent a title or
description without support; prefer abstain when uncertain. Titles must be
verbatim from evidence when available.

Respond with ONLY a JSON object of the form:
{"strategy": "complete", "proposals": [
  {"field": "title", "language": "zh", "script": "", "text": "译名",
   "kind": "translated", "confidence": 0.9,
   "reason": "short evidence citation", "source": "model"}
], "summary": "one sentence"}
Choose "abstain" with an empty proposals list when evidence is insufficient.
"""

_NORMALIZE_RE = re.compile(r"[\s\u3000]+")


def _schema_prompt() -> str:
    return (
        SYSTEM_PROMPT
        + "\nOutput must validate against this JSON schema:\n"
        + json.dumps(
            InfoCompletionOutput.model_json_schema(),
            ensure_ascii=False,
        )
    )


class InfoCompletionSkill:
    name = SKILL_NAME
    version = SKILL_VERSION

    def complete(
        self,
        value: InfoCompletionInput,
        *,
        target_entity: Entity,
        agent_run: AgentRun,
        source_observation: Observation | None = None,
        apply: bool = False,
        min_confidence: float = 0.85,
    ) -> dict[str, Any]:
        """Run one bounded enrichment pass and persist reviewable claims."""
        web_artifacts = self._gather_web_evidence(value=value, agent_run=agent_run)
        step = self._create_step(value, agent_run)
        result, _ai_run = self._model_result(
            value, step=step, web_artifacts=web_artifacts
        )
        if result.strategy == "abstain":
            step.output = result.model_dump(mode="json")
            step.status = AgentStep.Status.SUCCEEDED
            step.finished_at = timezone.now()
            step.save(update_fields=["output", "status", "finished_at"])
            return {
                "claims": 0,
                "applied": 0,
                "abstained": 1,
                "strategy": "abstain",
            }

        claims = 0
        applied = 0
        for proposal in result.proposals:
            if not self._acceptable_proposal(proposal, value):
                continue
            evidence_strength = self._evidence_strength(proposal, web_artifacts)
            calibrated = round(proposal.confidence * evidence_strength, 4)
            claim = self._record_claim(
                proposal=proposal,
                value=value,
                target_entity=target_entity,
                agent_run=agent_run,
                step=step,
                source_observation=source_observation,
                web_artifacts=web_artifacts,
                evidence_strength=evidence_strength,
                calibrated_confidence=calibrated,
            )
            claims += 1
            if self._apply_proposal(
                proposal=proposal,
                target_entity=target_entity,
                source_observation=source_observation,
                claim=claim,
                apply=apply,
                min_confidence=min_confidence,
                calibrated_confidence=calibrated,
            ):
                applied += 1

        step.output = result.model_dump(mode="json")
        step.status = AgentStep.Status.SUCCEEDED
        step.finished_at = timezone.now()
        step.save(update_fields=["output", "status", "finished_at"])
        return {
            "claims": claims,
            "applied": applied,
            "abstained": 0,
            "strategy": "complete",
        }

    def _gather_web_evidence(
        self, *, value: InfoCompletionInput, agent_run: AgentRun
    ) -> tuple[SourceArtifact, ...]:
        """Search the web once per entity and persist content-addressed artifacts."""
        registry = create_default_tool_registry()
        try:
            tool = registry.get("web.search")
        except KeyError:
            return ()
        query = value.preferred_name or value.original_name
        if not query.strip():
            return ()
        parameters = {"query": query, "max_results": 5}
        step = AgentStep.objects.create(
            run=agent_run,
            sequence=self._next_sequence(agent_run),
            kind=AgentStep.Kind.TOOL,
            skill_name="",
            skill_version="",
            input_hash=_payload_hash(parameters),
            input=parameters,
            status=AgentStep.Status.RUNNING,
            started_at=timezone.now(),
        )
        invocation = ToolInvocation.objects.create(
            step=step,
            tool_name=tool.name,
            tool_version=tool.version,
            status=ToolInvocation.Status.RUNNING,
            parameters=parameters,
            parameter_hash=_payload_hash(parameters),
            idempotency_key=f"enrich:{value.entity_id}:{tool.name}",
            idempotency_scope=agent_run.idempotency_scope or "system",
            permission_scope=tool.permission,
            risk_level=tool.risk_level,
            has_side_effects=tool.has_side_effects,
        )
        try:
            output = tool.execute(parameters)
        except Exception as exc:
            invocation.status = ToolInvocation.Status.FAILED
            invocation.error = f"{type(exc).__name__}: {exc}"[:4000]
            invocation.finished_at = timezone.now()
            invocation.save(update_fields=["status", "error", "finished_at"])
            step.status = AgentStep.Status.FAILED
            step.error = invocation.error
            step.finished_at = timezone.now()
            step.save(update_fields=["status", "error", "finished_at"])
            return ()
        invocation.status = ToolInvocation.Status.SUCCEEDED
        invocation.result = output
        invocation.finished_at = timezone.now()
        invocation.save(update_fields=["status", "result", "finished_at"])
        step.output = output
        step.status = AgentStep.Status.SUCCEEDED
        step.finished_at = timezone.now()
        step.save(update_fields=["output", "status", "finished_at"])
        artifacts: list[SourceArtifact] = []
        for item in output.get("results") or []:
            if not item.get("url"):
                continue
            artifacts.append(
                capture_artifact(
                    payload=item,
                    kind=SourceArtifact.Kind.SEARCH_RESULT,
                    source_url=str(item["url"]),
                    tool_name=tool.name,
                    tool_version=tool.version,
                    tool_invocation=invocation,
                    metadata={
                        "title": str(item.get("title", "")),
                        "score": item.get("score"),
                    },
                )
            )
        return tuple(artifacts)

    def _model_result(
        self,
        value: InfoCompletionInput,
        *,
        step: AgentStep,
        web_artifacts: tuple[SourceArtifact, ...],
    ) -> tuple[InfoCompletionOutput, AIRun | None]:
        payload = {
            **value.model_dump(mode="json"),
            "web_evidence": [
                {
                    "title": artifact.metadata.get("title", ""),
                    "url": artifact.source_url,
                    "content": artifact.excerpt[:700],
                }
                for artifact in web_artifacts
            ],
        }
        ai_run = AIRun.objects.create(
            agent_step=step,
            use_case=USE_CASE,
            provider=ai_gateway.provider_name,
            model=ai_gateway.resolve_model(USE_CASE),
            prompt_version=PROMPT_VERSION,
            input_hash=_payload_hash(payload),
            input_metadata={"skill": SKILL_NAME},
            status=AIRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        usage: dict[str, Any] = {}
        result: InfoCompletionOutput | None = None
        try:
            output, usage = ai_gateway.complete_json(
                system_prompt=_schema_prompt(),
                payload=payload,
                use_case=USE_CASE,
            )
            result = InfoCompletionOutput.model_validate(output)
        except Exception as first_error:
            retried = self._retry_with_contract(payload=payload)
            if retried is not None:
                result, usage = retried
            else:
                ai_run.status = AIRun.Status.FAILED
                ai_run.error = f"{type(first_error).__name__}: {first_error}"[:4000]
                ai_run.finished_at = timezone.now()
                ai_run.save(update_fields=["status", "error", "finished_at"])
                step.error = "Model output did not match the enrichment contract."
                step.status = AgentStep.Status.FAILED
                step.finished_at = timezone.now()
                step.save(update_fields=["status", "error", "finished_at"])
                return (
                    InfoCompletionOutput(
                        strategy="abstain",
                        proposals=[],
                        summary="Model output did not match the enrichment contract.",
                    ),
                    ai_run,
                )

        ai_run.output = result.model_dump(mode="json")
        ai_run.status = AIRun.Status.SUCCEEDED
        ai_run.input_tokens = optional_non_negative_int(usage.get("input_tokens"))
        ai_run.output_tokens = optional_non_negative_int(usage.get("output_tokens"))
        ai_run.cost = optional_non_negative_decimal(usage.get("cost"))
        ai_run.finished_at = timezone.now()
        ai_run.save(
            update_fields=[
                "output",
                "status",
                "input_tokens",
                "output_tokens",
                "cost",
                "finished_at",
            ]
        )
        return result, ai_run

    def _retry_with_contract(
        self,
        *,
        payload: dict[str, Any],
    ) -> tuple[InfoCompletionOutput, dict[str, Any]] | None:
        """Retry once with an explicit contract example after a schema miss."""
        retry_prompt = (
            _schema_prompt()
            + "\nYour previous response did not match. Return exactly:\n"
            + json.dumps(
                {
                    "strategy": "complete",
                    "proposals": [],
                    "summary": "Retry with schema-compliant output.",
                },
                ensure_ascii=False,
            )
            + "\nwith your real proposals filled in."
        )
        try:
            output, usage = ai_gateway.complete_json(
                system_prompt=retry_prompt,
                payload=payload,
                use_case=USE_CASE,
            )
            return InfoCompletionOutput.model_validate(output), usage
        except Exception:
            logger.exception(
                "Enrichment model retry failed after contract mismatch",
            )
            return None

    @staticmethod
    def _acceptable_proposal(
        proposal: FieldProposal, value: InfoCompletionInput
    ) -> bool:
        target_languages = {lang.split(":", 1)[-1] for lang in value.missing_fields}
        if target_languages and proposal.language not in target_languages:
            return False
        normalized = InfoCompletionSkill._normalize(proposal.text)
        if not normalized:
            return False
        for existing in value.existing_names.values():
            if InfoCompletionSkill._normalize(existing) == normalized:
                return False
        return True

    @staticmethod
    def _evidence_strength(
        proposal: FieldProposal, web_artifacts: tuple[SourceArtifact, ...]
    ) -> float:
        return 1.0 if proposal.source == "web" and web_artifacts else 0.9

    @staticmethod
    def _record_claim(
        *,
        proposal: FieldProposal,
        value: InfoCompletionInput,
        target_entity: Entity,
        agent_run: AgentRun,
        step: AgentStep,
        source_observation: Observation | None,
        web_artifacts: tuple[SourceArtifact, ...],
        evidence_strength: float,
        calibrated_confidence: float,
    ) -> AIClaim:
        claim = AIClaim.objects.create(
            step=step,
            target_entity=target_entity,
            claim_type=SKILL_NAME,
            predicate_slug=f"entity:{proposal.field}",
            proposed_value=proposal.model_dump(mode="json"),
            model_confidence=proposal.confidence,
            evidence_strength=evidence_strength,
            calibrated_confidence=calibrated_confidence,
        )
        if source_observation is not None:
            ClaimEvidence.objects.create(
                claim=claim,
                observation=source_observation,
                locator=f"/{proposal.field}:{proposal.language}",
                excerpt=value.preferred_name[:4000],
                excerpt_hash=_payload_hash(
                    {"text": value.preferred_name, "language": proposal.language}
                ),
                relevance=1,
            )
        for artifact in web_artifacts:
            if proposal.source == "web":
                ClaimEvidence.objects.create(
                    claim=claim,
                    artifact=artifact,
                    locator=f"artifact:{artifact.content_hash[:16]}",
                    excerpt=artifact.excerpt[:4000],
                    excerpt_hash=artifact.content_hash,
                    relevance=1,
                )
        return claim

    @staticmethod
    def _apply_proposal(
        *,
        proposal: FieldProposal,
        target_entity: Entity,
        source_observation: Observation | None,
        claim: AIClaim,
        apply: bool,
        min_confidence: float,
        calibrated_confidence: float,
    ) -> bool:
        """Auto-apply only high-confidence title names; descriptions stay claims."""
        if proposal.field != "title":
            return False
        if not apply or calibrated_confidence < min_confidence:
            return False
        provider_record = (
            source_observation.provider_record
            if source_observation is not None
            else None
        )
        created = EntityName.objects.get_or_create(
            entity=target_entity,
            text=proposal.text.strip(),
            language=proposal.language,
            kind=proposal.kind,
            defaults={
                "script": proposal.script,
                "is_official": proposal.kind == "official",
                "is_original": False,
                "is_machine_generated": True,
                "is_reviewed": False,
                "provider_record": provider_record,
                "observation": source_observation,
            },
        )
        if created[1]:
            claim.status = AIClaim.Status.ACCEPTED
            claim.policy_decision = "auto_apply"
            claim.policy_reason = (
                f"Confidence {calibrated_confidence} >= {min_confidence} threshold."
            )
            claim.decided_at = timezone.now()
            claim.save(
                update_fields=[
                    "status",
                    "policy_decision",
                    "policy_reason",
                    "decided_at",
                ]
            )
            return True
        claim.status = AIClaim.Status.SUPERSEDED
        claim.policy_decision = "duplicate_name"
        claim.policy_reason = "An identical entity name already exists."
        claim.decided_at = timezone.now()
        claim.save(
            update_fields=["status", "policy_decision", "policy_reason", "decided_at"]
        )
        return False

    @staticmethod
    def _create_step(value: InfoCompletionInput, agent_run: AgentRun) -> AgentStep:
        return AgentStep.objects.create(
            run=agent_run,
            sequence=InfoCompletionSkill._next_sequence(agent_run),
            kind=AgentStep.Kind.SKILL,
            skill_name=SKILL_NAME,
            skill_version=SKILL_VERSION,
            input_hash=_payload_hash(value.model_dump(mode="json")),
            input=value.model_dump(mode="json"),
            status=AgentStep.Status.RUNNING,
            started_at=timezone.now(),
        )

    @staticmethod
    def _next_sequence(agent_run: AgentRun) -> int:
        last = (
            AgentStep.objects.filter(run=agent_run)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
        )
        return (last + 1) if last is not None else 0

    @staticmethod
    def _normalize(value: str) -> str:
        return _NORMALIZE_RE.sub("", value.strip().lower())

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            name=SKILL_NAME,
            description="Complete missing multilingual titles and descriptions.",
            version=SKILL_VERSION,
            prompt_version=PROMPT_VERSION,
            input_model=InfoCompletionInput,
            output_model=InfoCompletionOutput,
            handler=self.complete,
            use_case=USE_CASE,
        )


info_completion_skill = InfoCompletionSkill()
skill_registry.register(info_completion_skill.definition)


def _payload_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
