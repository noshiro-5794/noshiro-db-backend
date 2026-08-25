"""Evidence-first normalization of provider vocabulary."""

from __future__ import annotations

import hashlib
import json
import unicodedata

from django.db import transaction
from django.utils import timezone

from apps.ai.models import (
    AgentRun,
    AgentStep,
    AIClaim,
    AIRun,
    ClaimEvidence,
    SourceArtifact,
)
from apps.ai.services.common import (
    optional_non_negative_decimal,
    optional_non_negative_int,
)
from apps.index.models import Entity, Observation, ProviderRepresentation, TermAlias
from integrations.ai.gateway import ai_gateway

from ..registry import SkillDefinition, skill_registry
from .schemas import FieldNormalizationInput, FieldNormalizationOutput

SKILL_NAME = "field_normalization"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "field-normalization-v1"
USE_CASE = "field_normalization"

SYSTEM_PROMPT = """You normalize provider vocabulary for a knowledge base.
Use only the supplied raw value and context. Never invent an existing term slug.
Choose preserve_raw or abstain when the value is a title, identifier, or ambiguous.
Return JSON matching the supplied schema with action, confidence, and reason.
"""


class FieldNormalizationSkill:
    name = SKILL_NAME
    version = SKILL_VERSION

    def normalize(
        self,
        value: FieldNormalizationInput,
        *,
        target_entity: Entity | None = None,
        agent_run: AgentRun | None = None,
        source_observation: Observation | None = None,
        source_artifact: SourceArtifact | None = None,
    ) -> FieldNormalizationOutput:
        if (target_entity is None) != (agent_run is None):
            raise ValueError("target_entity and agent_run must be supplied together.")
        if target_entity is not None and (
            (source_observation is None) == (source_artifact is None)
        ):
            raise ValueError("Normalizing a target entity requires exactly one source.")
        normalized_key = self.normalize_key(value.source_text)
        language = value.language or self.detect_language(value.source_text)
        step = self._create_step(value, agent_run) if agent_run else None
        alias = self._lookup_alias(value, normalized_key, language)
        if alias is not None:
            result = FieldNormalizationOutput(
                action="map_existing",
                normalized_key=alias.normalized_key,
                preferred_term=alias.preferred_term,
                language=alias.language or language,
                script=alias.script,
                confidence=float(alias.confidence),
                reason="Matched a reviewed provider vocabulary alias.",
                existing_term_slug=alias.term.slug if alias.term_id else "",
                source="alias",
            )
            if step is not None:
                step.output = result.model_dump(mode="json")
                step.status = AgentStep.Status.SUCCEEDED
                step.finished_at = timezone.now()
                step.save(update_fields=["output", "status", "finished_at"])
        else:
            result, _ai_run = self._model_result(
                value, normalized_key, language, step=step
            )
            if step is not None:
                step.output = result.model_dump(mode="json")
                fields = ["output"]
                if step.status == AgentStep.Status.RUNNING:
                    step.status = AgentStep.Status.SUCCEEDED
                    step.finished_at = timezone.now()
                    fields.extend(["status", "finished_at"])
                step.save(update_fields=fields)

        if target_entity is not None and agent_run is not None:
            self.record_claim(
                result=result,
                source_text=value.source_text,
                vocabulary=value.vocabulary,
                target_entity=target_entity,
                agent_run=agent_run,
                step=step,
                source_observation=source_observation,
                source_artifact=source_artifact,
            )
        return result

    @staticmethod
    def normalize_key(value: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", value).lower().split())

    @staticmethod
    def detect_language(value: str) -> str:
        for char in value:
            name = unicodedata.name(char, "")
            if "HIRAGANA" in name or "KATAKANA" in name:
                return "ja"
            if "HANGUL" in name:
                return "ko"
            if "CJK" in name:
                return "zh"
        return "en"

    @staticmethod
    def _lookup_alias(
        value: FieldNormalizationInput, normalized_key: str, language: str
    ) -> TermAlias | None:
        aliases = TermAlias.objects.filter(
            vocabulary=value.vocabulary,
            normalized_key=normalized_key,
            is_reviewed=True,
            term__isnull=False,
        ).select_related("term")
        if value.provider_namespace:
            aliases = aliases.filter(
                provider_namespace__slug=value.provider_namespace,
            )
        else:
            aliases = aliases.filter(provider_namespace__isnull=True)
        return (
            aliases.filter(language__in=[language, ""])
            .order_by("-confidence", "id")
            .first()
        )

    def _model_result(
        self,
        value: FieldNormalizationInput,
        normalized_key: str,
        language: str,
        *,
        step: AgentStep | None = None,
    ) -> tuple[FieldNormalizationOutput, AIRun | None]:
        payload = {
            "vocabulary": value.vocabulary,
            "source_text": value.source_text,
            "normalized_key": normalized_key,
            "provider_namespace": value.provider_namespace,
            "language": language,
            "context": value.context,
        }
        ai_run = None
        started = timezone.now()
        if step is not None:
            ai_run = AIRun.objects.create(
                agent_step=step,
                use_case=USE_CASE,
                provider=ai_gateway.provider_name,
                model=ai_gateway.resolve_model(USE_CASE),
                prompt_version=PROMPT_VERSION,
                input_hash=_payload_hash(payload),
                input_metadata={"skill": SKILL_NAME},
                status=AIRun.Status.RUNNING,
                started_at=started,
            )
        try:
            output, usage = ai_gateway.complete_json(
                system_prompt=SYSTEM_PROMPT,
                payload=payload,
                use_case=USE_CASE,
            )
            result = FieldNormalizationOutput.model_validate(
                {**output, "source": "model"}
            )
        except Exception as exc:
            if ai_run is not None:
                ai_run.status = AIRun.Status.FAILED
                ai_run.error = f"{type(exc).__name__}: {exc}"[:4000]
                ai_run.finished_at = timezone.now()
                ai_run.save(update_fields=["status", "error", "finished_at"])
            if step is not None:
                step.error = "Model unavailable or returned an invalid contract."
                step.status = AgentStep.Status.FAILED
                step.finished_at = timezone.now()
                step.save(update_fields=["status", "error", "finished_at"])
            return FieldNormalizationOutput(
                action="preserve_raw",
                normalized_key=normalized_key,
                preferred_term=value.source_text.strip(),
                language=language,
                confidence=0,
                reason="Model unavailable or returned an invalid contract.",
                source="raw",
            ), ai_run

        if result.action == "map_existing" and not result.existing_term_slug:
            result = result.model_copy(
                update={
                    "action": "propose_new",
                    "reason": "Model selected map_existing without a stable term slug.",
                }
            )

        if ai_run is not None:
            ai_run.output = result.model_dump(mode="json")
            ai_run.status = AIRun.Status.SUCCEEDED
            ai_run.input_tokens = optional_non_negative_int(usage.get("input_tokens"))
            ai_run.output_tokens = optional_non_negative_int(usage.get("output_tokens"))
            ai_run.cost = optional_non_negative_decimal(usage.get("cost"))
            ai_run.latency_ms = max(
                0, int((timezone.now() - started).total_seconds() * 1000)
            )
            ai_run.finished_at = timezone.now()
            ai_run.save(
                update_fields=[
                    "output",
                    "status",
                    "input_tokens",
                    "output_tokens",
                    "cost",
                    "latency_ms",
                    "finished_at",
                ]
            )
        return result, ai_run

    @staticmethod
    @transaction.atomic
    def _create_step(value: FieldNormalizationInput, agent_run: AgentRun) -> AgentStep:
        AgentRun.objects.select_for_update().get(pk=agent_run.pk)
        last_sequence = (
            AgentStep.objects.filter(run=agent_run)
            .order_by("-sequence")
            .values_list("sequence", flat=True)
            .first()
        )
        return AgentStep.objects.create(
            run=agent_run,
            sequence=(last_sequence + 1) if last_sequence is not None else 0,
            kind=AgentStep.Kind.SKILL,
            skill_name=SKILL_NAME,
            skill_version=SKILL_VERSION,
            input_hash=_payload_hash(value.model_dump(mode="json")),
            input=value.model_dump(mode="json"),
            status=AgentStep.Status.RUNNING,
            started_at=timezone.now(),
        )

    @staticmethod
    @transaction.atomic
    def record_claim(
        *,
        result: FieldNormalizationOutput,
        source_text: str,
        vocabulary: str,
        target_entity: Entity,
        agent_run: AgentRun,
        step: AgentStep | None = None,
        source_observation: Observation | None = None,
        source_artifact: SourceArtifact | None = None,
    ) -> AIClaim:
        if (source_observation is None) == (source_artifact is None):
            raise ValueError("Claim evidence requires exactly one source.")
        if (
            source_observation is not None
            and not ProviderRepresentation.objects.filter(
                provider_record=source_observation.provider_record,
                entity=target_entity,
                is_active=True,
            ).exists()
        ):
            raise ValueError(
                "Observation is not an active source for the target entity."
            )
        if (
            source_artifact is not None
            and source_artifact.tool_invocation_id is not None
            and source_artifact.tool_invocation.step.run_id != agent_run.pk
        ):
            raise ValueError("Artifact does not belong to the current agent run.")
        if step is None:
            AgentRun.objects.select_for_update().get(pk=agent_run.pk)
            last_sequence = (
                AgentStep.objects.filter(run=agent_run)
                .order_by("-sequence")
                .values_list("sequence", flat=True)
                .first()
            )
            step = AgentStep.objects.create(
                run=agent_run,
                sequence=(last_sequence + 1) if last_sequence is not None else 0,
                kind=AgentStep.Kind.SKILL,
                skill_name=SKILL_NAME,
                skill_version=SKILL_VERSION,
                input={"source_text": source_text, "vocabulary": vocabulary},
            )
        claim = AIClaim.objects.create(
            step=step,
            target_entity=target_entity,
            claim_type=SKILL_NAME,
            predicate_slug=f"taxonomy:{vocabulary}",
            proposed_value=result.model_dump(mode="json"),
            model_confidence=result.confidence,
            evidence_strength=1 if result.source == "alias" else 0,
        )
        ClaimEvidence.objects.create(
            claim=claim,
            observation=source_observation,
            artifact=source_artifact,
            locator="/source_text",
            excerpt=source_text[:4000],
            excerpt_hash=_payload_hash({"source_text": source_text}),
        )
        return claim

    @property
    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            name=SKILL_NAME,
            description="Normalize provider vocabulary into reviewed taxonomy terms.",
            version=SKILL_VERSION,
            prompt_version=PROMPT_VERSION,
            input_model=FieldNormalizationInput,
            output_model=FieldNormalizationOutput,
            handler=self.normalize,
            use_case=USE_CASE,
        )


field_normalization_skill = FieldNormalizationSkill()
skill_registry.register(field_normalization_skill.definition)


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
