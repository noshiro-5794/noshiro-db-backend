import hashlib
import json
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.exceptions import AIInputNotAllowed, InvalidAIProposal
from apps.ai.models import AIProposal, AIRun
from apps.index.models import (
    ContentSafety,
    CurrentObservation,
    Entity,
    Observation,
    Predicate,
    Provider,
    ProviderRepresentation,
    Work,
)
from apps.index.selectors.projections import entity_detail
from apps.index.services import entity_resolution_service
from integrations.ai import ai_gateway

from .common import optional_non_negative_decimal, optional_non_negative_int


class AIKnowledgeProposalService:
    CLASSIFICATION_USE_CASE = "entity_classification"
    CLASSIFICATION_PROMPT_VERSION = "entity-classification-v1"
    EXTRACTION_USE_CASE = "evidence_extraction"
    EXTRACTION_PROMPT_VERSION = "evidence-extraction-v1"
    MAX_INPUT_BYTES = 100_000
    MAX_CLAIMS = 100

    def classify_entity(self, *, entity_id) -> AIProposal:
        entity = entity_resolution_service.resolve(Entity.objects.get(pk=entity_id))
        if entity.kind != Entity.Kind.WORK:
            raise AIInputNotAllowed("Only work entities can be classified.")
        if not entity_resolution_service.is_public(entity):
            return self._abstain_by_policy(
                use_case=self.CLASSIFICATION_USE_CASE,
                prompt_version=self.CLASSIFICATION_PROMPT_VERSION,
                input_metadata={"entity_id": str(entity.id)},
                target_entity=entity,
                output={
                    "work_type": "abstain",
                    "confidence": "0",
                    "reason": "Restricted entities cannot be sent to an AI provider.",
                },
            )
        disallowed_providers = list(
            ProviderRepresentation.objects.filter(
                entity_id__in=entity_resolution_service.cluster_ids(entity),
                is_active=True,
            )
            .exclude(
                provider_record__namespace__provider__ai_usage_policy=(
                    Provider.UsagePolicy.ALLOWED
                )
            )
            .values_list("provider_record__namespace__provider__slug", flat=True)
            .distinct()
            .order_by("provider_record__namespace__provider__slug")
        )
        if disallowed_providers:
            providers = ", ".join(disallowed_providers)
            return self._abstain_by_policy(
                use_case=self.CLASSIFICATION_USE_CASE,
                prompt_version=self.CLASSIFICATION_PROMPT_VERSION,
                input_metadata={"entity_id": str(entity.id)},
                target_entity=entity,
                output={
                    "work_type": "abstain",
                    "confidence": "0",
                    "reason": (
                        "Every represented provider must explicitly allow AI processing; "
                        f"blocked by: {providers}."
                    ),
                },
            )
        payload = entity_detail(entity, safe=True)
        output, run, usage, latency_ms = self._complete(
            use_case=self.CLASSIFICATION_USE_CASE,
            prompt_version=self.CLASSIFICATION_PROMPT_VERSION,
            input_metadata={"entity_id": str(entity.id)},
            system_prompt=(
                "Classify a public knowledge-base work using only the supplied safe "
                "projection. Return a JSON object with work_type, confidence, and a "
                "concise reason. work_type must be anime, galgame, manga, novel, game, "
                "music, other, unclassified, or abstain. Never infer private identities."
            ),
            payload=payload,
            validator=self._validate_classification,
        )
        return self._persist_proposal(
            run=run,
            proposal_type=self.CLASSIFICATION_USE_CASE,
            output=output,
            confidence=Decimal(output["confidence"]),
            target_entity=entity,
            usage=usage,
            latency_ms=latency_ms,
            abstained=output["work_type"] == "abstain",
        )

    def extract_evidence(self, *, observation_id, entity_id) -> AIProposal:
        observation = Observation.objects.select_related(
            "provider_record__namespace__provider"
        ).get(pk=observation_id)
        entity = entity_resolution_service.resolve(Entity.objects.get(pk=entity_id))
        if not ProviderRepresentation.objects.filter(
            provider_record=observation.provider_record,
            entity_id__in=entity_resolution_service.cluster_ids(entity),
            is_active=True,
        ).exists():
            raise AIInputNotAllowed(
                "Observation is not an active representation of the target entity."
            )
        if not CurrentObservation.objects.filter(
            provider_record=observation.provider_record,
            observation=observation,
        ).exists():
            raise AIInputNotAllowed("Only a current observation can be processed.")
        provider = observation.provider_record.namespace.provider
        metadata = {
            "entity_id": str(entity.id),
            "observation_id": str(observation.id),
            "provider": provider.slug,
        }
        if provider.ai_usage_policy != Provider.UsagePolicy.ALLOWED:
            return self._abstain_by_policy(
                use_case=self.EXTRACTION_USE_CASE,
                prompt_version=self.EXTRACTION_PROMPT_VERSION,
                input_metadata=metadata,
                target_entity=entity,
                source_observation=observation,
                output={
                    "claims": [],
                    "reason": "Provider policy does not explicitly allow AI processing.",
                },
            )
        if not entity_resolution_service.is_public(entity):
            return self._abstain_by_policy(
                use_case=self.EXTRACTION_USE_CASE,
                prompt_version=self.EXTRACTION_PROMPT_VERSION,
                input_metadata=metadata,
                target_entity=entity,
                source_observation=observation,
                output={
                    "claims": [],
                    "reason": "Restricted entities cannot be sent to an AI provider.",
                },
            )
        payload = {
            "entity_id": str(entity.id),
            "provider": provider.slug,
            "schema_name": observation.schema_name,
            "schema_version": observation.schema_version,
            "normalized_data": observation.normalized_data,
        }
        output, run, usage, latency_ms = self._complete(
            use_case=self.EXTRACTION_USE_CASE,
            prompt_version=self.EXTRACTION_PROMPT_VERSION,
            input_metadata=metadata,
            system_prompt=(
                "Extract only explicitly stated facts from the supplied provider "
                "observation. Return a JSON object with a claims array. Each claim must "
                "contain predicate, value, value_type, language, spoiler_level, safety, "
                "json_pointer, and confidence. Use an empty claims array when evidence is "
                "insufficient. Do not infer aliases, private identities, or unstated facts."
            ),
            payload=payload,
            validator=self._validate_extraction,
        )
        return self._persist_proposal(
            run=run,
            proposal_type=self.EXTRACTION_USE_CASE,
            output=output,
            confidence=self._claims_confidence(output["claims"]),
            target_entity=entity,
            source_observation=observation,
            usage=usage,
            latency_ms=latency_ms,
            abstained=not output["claims"],
        )

    def _complete(
        self,
        *,
        use_case: str,
        prompt_version: str,
        input_metadata: dict[str, Any],
        system_prompt: str,
        payload: dict[str, Any],
        validator,
    ) -> tuple[dict[str, Any], AIRun, dict[str, Any], int]:
        encoded = self._encoded_payload(payload)
        run = AIRun.objects.create(
            use_case=use_case,
            provider=ai_gateway.provider_name,
            model=ai_gateway.model_name,
            prompt_version=prompt_version,
            input_hash=hashlib.sha256(encoded).hexdigest(),
            input_metadata=input_metadata,
            status=AIRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        started = timezone.now()
        try:
            raw_output, usage = ai_gateway.complete_json(
                system_prompt=system_prompt,
                payload=payload,
            )
            output = validator(raw_output)
        except Exception as exc:
            run.status = AIRun.Status.FAILED
            run.error = f"{type(exc).__name__}: {exc}"[:4000]
            run.finished_at = timezone.now()
            run.save(update_fields=["status", "error", "finished_at"])
            raise
        latency_ms = int((timezone.now() - started).total_seconds() * 1000)
        return output, run, usage, latency_ms

    def _encoded_payload(self, payload: dict[str, Any]) -> bytes:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode()
        if len(encoded) > self.MAX_INPUT_BYTES:
            raise AIInputNotAllowed(
                f"AI input exceeds the {self.MAX_INPUT_BYTES}-byte safety limit."
            )
        return encoded

    @staticmethod
    def _validate_confidence(value: Any) -> Decimal:
        if isinstance(value, bool):
            raise InvalidAIProposal("AI confidence must be a number from 0 to 1.")
        try:
            confidence = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidAIProposal(
                "AI confidence must be a number from 0 to 1."
            ) from exc
        if not math.isfinite(float(confidence)) or not 0 <= confidence <= 1:
            raise InvalidAIProposal("AI confidence must be a number from 0 to 1.")
        return confidence

    @classmethod
    def _validate_classification(cls, output: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(output, dict):
            raise InvalidAIProposal("AI classification output must be an object.")
        work_type = output.get("work_type")
        allowed = set(Work.WorkType.values) | {"abstain"}
        if work_type not in allowed:
            raise InvalidAIProposal("AI work_type is invalid.")
        reason = output.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidAIProposal("AI classification reason is required.")
        confidence = cls._validate_confidence(output.get("confidence"))
        return {
            "work_type": work_type,
            "confidence": str(confidence),
            "reason": reason.strip()[:2000],
        }

    @classmethod
    def _validate_extraction(cls, output: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(output, dict):
            raise InvalidAIProposal("AI extraction output must be an object.")
        claims = output.get("claims")
        if not isinstance(claims, list) or len(claims) > cls.MAX_CLAIMS:
            raise InvalidAIProposal(
                f"AI claims must be a list with at most {cls.MAX_CLAIMS} items."
            )
        validated = []
        value_types = set(Predicate.ValueType.values)
        safety_values = set(ContentSafety.values)
        for claim in claims:
            if not isinstance(claim, dict):
                raise InvalidAIProposal("Each AI claim must be an object.")
            predicate = claim.get("predicate")
            if (
                not isinstance(predicate, str)
                or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", predicate) is None
                or len(predicate) > 128
            ):
                raise InvalidAIProposal("AI claim predicate is invalid.")
            value_type = claim.get("value_type")
            if value_type not in value_types:
                raise InvalidAIProposal("AI claim value_type is invalid.")
            language = claim.get("language", "")
            if not isinstance(language, str) or len(language) > 35:
                raise InvalidAIProposal("AI claim language is invalid.")
            spoiler_level = claim.get("spoiler_level", 0)
            if isinstance(spoiler_level, bool) or not isinstance(spoiler_level, int):
                raise InvalidAIProposal("AI claim spoiler_level is invalid.")
            if not 0 <= spoiler_level <= 3:
                raise InvalidAIProposal("AI claim spoiler_level is invalid.")
            safety = claim.get("safety", ContentSafety.UNKNOWN)
            if safety not in safety_values:
                raise InvalidAIProposal("AI claim safety is invalid.")
            pointer = claim.get("json_pointer")
            if not isinstance(pointer, str) or not pointer.startswith("/"):
                raise InvalidAIProposal("AI claim json_pointer is invalid.")
            confidence = cls._validate_confidence(claim.get("confidence"))
            validated.append(
                {
                    "predicate": predicate,
                    "value": claim.get("value"),
                    "value_type": value_type,
                    "language": language,
                    "spoiler_level": spoiler_level,
                    "safety": safety,
                    "json_pointer": pointer[:512],
                    "confidence": str(confidence),
                }
            )
        return {"claims": validated}

    @staticmethod
    def _claims_confidence(claims: list[dict[str, Any]]) -> Decimal:
        if not claims:
            return Decimal("0")
        return min(Decimal(claim["confidence"]) for claim in claims)

    @staticmethod
    @transaction.atomic
    def _persist_proposal(
        *,
        run: AIRun,
        proposal_type: str,
        output: dict[str, Any],
        confidence: Decimal,
        target_entity: Entity,
        usage: dict[str, Any],
        latency_ms: int,
        abstained: bool,
        source_observation: Observation | None = None,
    ) -> AIProposal:
        run.status = AIRun.Status.SUCCEEDED
        run.output = output
        run.input_tokens = optional_non_negative_int(usage.get("input_tokens"))
        run.output_tokens = optional_non_negative_int(usage.get("output_tokens"))
        run.cost = optional_non_negative_decimal(usage.get("cost"))
        run.latency_ms = max(0, latency_ms)
        run.finished_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "output",
                "input_tokens",
                "output_tokens",
                "cost",
                "latency_ms",
                "finished_at",
            ]
        )
        return AIProposal.objects.create(
            run=run,
            target_entity=target_entity,
            source_observation=source_observation,
            proposal_type=proposal_type,
            payload=output,
            confidence=confidence,
            status=(
                AIProposal.Status.ABSTAINED if abstained else AIProposal.Status.PENDING
            ),
            policy_reason=(
                "The model abstained; no canonical write was performed."
                if abstained
                else "Shadow proposal only; no canonical write was performed."
            ),
            decided_at=timezone.now() if abstained else None,
        )

    @staticmethod
    @transaction.atomic
    def _abstain_by_policy(
        *,
        use_case: str,
        prompt_version: str,
        input_metadata: dict[str, Any],
        target_entity: Entity,
        output: dict[str, Any],
        source_observation: Observation | None = None,
    ) -> AIProposal:
        now = timezone.now()
        reason = str(output["reason"])
        run = AIRun.objects.create(
            use_case=use_case,
            provider="policy_gate",
            model="none",
            prompt_version=prompt_version,
            input_hash=hashlib.sha256(
                json.dumps(input_metadata, sort_keys=True).encode()
            ).hexdigest(),
            input_metadata=input_metadata,
            output=output,
            status=AIRun.Status.ABSTAINED,
            started_at=now,
            finished_at=now,
        )
        return AIProposal.objects.create(
            run=run,
            target_entity=target_entity,
            source_observation=source_observation,
            proposal_type=use_case,
            payload=output,
            confidence=0,
            status=AIProposal.Status.ABSTAINED,
            policy_reason=reason,
            decided_at=now,
        )


ai_knowledge_proposal_service = AIKnowledgeProposalService()
