import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.exceptions import InvalidAIProposal
from apps.ai.models import AIEvaluationRun, AIPolicy, AIProposal, AIRun
from apps.index.models import MatchCandidate, MatchDecision
from apps.index.services import entity_resolution_service
from apps.users.models import UserSubject
from integrations.ai import ai_gateway


class AIMatchingService:
    USE_CASE = "entity_matching"
    PROMPT_VERSION = "entity-match-v1"
    DECISIONS = frozenset({"bind", "reject", "abstain"})

    @staticmethod
    def _input_hash(payload: dict[str, Any]) -> str:
        value = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(value).hexdigest()

    def evaluate(self, *, candidate_id) -> AIProposal:
        candidate = MatchCandidate.objects.select_related(
            "left_entity", "right_entity"
        ).get(pk=candidate_id)
        policy, _ = AIPolicy.objects.get_or_create(
            use_case=self.USE_CASE,
            defaults={"policy_version": candidate.policy_version},
        )
        evidence = [
            {
                "evidence_type": item["evidence_type"],
                "value": item["value"],
                "weight": str(item["weight"]),
            }
            for item in candidate.evidence.order_by("evidence_type").values(
                "evidence_type", "value", "weight"
            )
        ]
        payload = {
            "left_entity_id": str(candidate.left_entity_id),
            "right_entity_id": str(candidate.right_entity_id),
            "resolver_score": str(candidate.score),
            "runner_up_margin": str(candidate.runner_up_margin),
            "hard_conflicts": candidate.hard_conflicts,
            "evidence": evidence,
        }
        run = AIRun.objects.create(
            use_case=self.USE_CASE,
            provider=ai_gateway.provider_name,
            model=ai_gateway.model_name,
            prompt_version=self.PROMPT_VERSION,
            input_hash=self._input_hash(payload),
            input_metadata={"candidate_id": str(candidate.id)},
            status=AIRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        started = timezone.now()
        try:
            raw_output, usage = ai_gateway.complete_json(
                system_prompt=(
                    "Assess whether two knowledge-base entities represent the same "
                    "real work using only the supplied evidence. Never infer a private "
                    "identity. Return a JSON object with decision (bind, reject, or "
                    "abstain), confidence from 0 to 1, and a concise reason."
                ),
                payload=payload,
            )
            output = self._validate_output(raw_output)
        except Exception as exc:
            self._mark_run_failed(run=run, error=exc)
            raise

        latency_ms = int((timezone.now() - started).total_seconds() * 1000)
        return self._persist_result(
            run=run,
            candidate_id=candidate.id,
            policy_id=policy.id,
            output=output,
            usage=usage,
            latency_ms=latency_ms,
        )

    @classmethod
    def _validate_output(cls, output: dict[str, Any]) -> dict[str, Any]:
        decision = output.get("decision")
        reason = output.get("reason")
        raw_confidence = output.get("confidence")
        if decision not in cls.DECISIONS:
            raise InvalidAIProposal(
                "AI proposal decision must be bind, reject, or abstain."
            )
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidAIProposal("AI proposal reason must be a non-empty string.")
        if isinstance(raw_confidence, bool):
            raise InvalidAIProposal(
                "AI proposal confidence must be a number from 0 to 1."
            )
        try:
            confidence = Decimal(str(raw_confidence))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidAIProposal(
                "AI proposal confidence must be a number from 0 to 1."
            ) from exc
        if not math.isfinite(float(confidence)) or not 0 <= confidence <= 1:
            raise InvalidAIProposal(
                "AI proposal confidence must be a number from 0 to 1."
            )
        return {
            "decision": decision,
            "confidence": str(confidence),
            "reason": reason.strip()[:2000],
        }

    @staticmethod
    def _mark_run_failed(*, run: AIRun, error: Exception) -> None:
        run.status = AIRun.Status.FAILED
        run.error = f"{type(error).__name__}: {error}"[:4000]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])

    @transaction.atomic
    def _persist_result(
        self,
        *,
        run: AIRun,
        candidate_id,
        policy_id: int,
        output: dict[str, Any],
        usage: dict[str, Any],
        latency_ms: int,
    ) -> AIProposal:
        candidate = MatchCandidate.objects.select_for_update().get(pk=candidate_id)
        policy = AIPolicy.objects.get(pk=policy_id)
        run.status = AIRun.Status.SUCCEEDED
        run.output = output
        run.input_tokens = self._optional_non_negative_int(usage.get("input_tokens"))
        run.output_tokens = self._optional_non_negative_int(usage.get("output_tokens"))
        run.cost = self._optional_non_negative_decimal(usage.get("cost"))
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
        proposal = AIProposal.objects.create(
            run=run,
            match_candidate=candidate,
            proposal_type=self.USE_CASE,
            payload=output,
            confidence=Decimal(output["confidence"]),
        )
        self._apply_policy(proposal=proposal, candidate=candidate, policy=policy)
        return proposal

    @staticmethod
    def _optional_non_negative_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _optional_non_negative_decimal(value: Any) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() and parsed >= 0 else None

    @staticmethod
    def _policy_is_production_ready(
        *, policy: AIPolicy, candidate: MatchCandidate
    ) -> bool:
        if (
            not policy.is_enabled
            or policy.shadow_mode
            or policy.policy_version != candidate.policy_version
        ):
            return False
        evaluation = (
            AIEvaluationRun.objects.filter(
                use_case=policy.use_case,
                policy_version=policy.policy_version,
                passed=True,
            )
            .order_by("-created_at")
            .first()
        )
        return bool(
            evaluation
            and evaluation.sample_count > 0
            and evaluation.precision >= policy.required_evaluation_precision
        )

    @staticmethod
    def _has_conflicting_user_library_data(candidate: MatchCandidate) -> bool:
        left_users = UserSubject.objects.filter(
            entity_id=candidate.left_entity_id
        ).values("user_id")
        return UserSubject.objects.filter(
            entity_id=candidate.right_entity_id,
            user_id__in=left_users,
        ).exists()

    def _apply_policy(
        self,
        *,
        proposal: AIProposal,
        candidate: MatchCandidate,
        policy: AIPolicy,
    ) -> None:
        if candidate.status != MatchCandidate.Status.PENDING:
            self._finish_proposal(
                proposal,
                status=AIProposal.Status.ABSTAINED,
                reason="Candidate was already decided by another run.",
            )
            return
        if not self._policy_is_production_ready(policy=policy, candidate=candidate):
            proposal.policy_reason = (
                "Shadow proposal only; policy is disabled, version-mismatched, "
                "or has not passed its production evaluation gate."
            )
            proposal.save(update_fields=["policy_reason"])
            return

        evidence_types = candidate.evidence.values("evidence_type").distinct().count()
        bind_allowed = all(
            (
                proposal.payload["decision"] == MatchDecision.Outcome.BIND,
                proposal.confidence >= policy.minimum_score,
                candidate.score >= policy.minimum_score,
                candidate.runner_up_margin >= policy.minimum_margin,
                evidence_types >= policy.minimum_evidence_types,
                candidate.left_entity.kind == candidate.right_entity.kind,
                not candidate.hard_conflicts,
                not self._has_conflicting_user_library_data(candidate),
            )
        )
        if bind_allowed:
            reason = "Passed calibrated conservative auto-bind gate."
            self._finish_proposal(
                proposal,
                status=AIProposal.Status.ACCEPTED,
                reason=reason,
            )
            entity_resolution_service.decide_candidate(
                candidate=candidate,
                outcome=MatchDecision.Outcome.BIND,
                decided_by="ai_policy",
                reason=reason,
            )
            return

        reason = "Conservative policy abstained because one or more bind gates failed."
        self._finish_proposal(
            proposal,
            status=AIProposal.Status.ABSTAINED,
            reason=reason,
        )
        entity_resolution_service.decide_candidate(
            candidate=candidate,
            outcome=MatchDecision.Outcome.ABSTAIN,
            decided_by="ai_policy",
            reason=reason,
        )

    @staticmethod
    def _finish_proposal(proposal: AIProposal, *, status: str, reason: str) -> None:
        proposal.status = status
        proposal.policy_reason = reason
        proposal.decided_at = timezone.now()
        proposal.save(update_fields=["status", "policy_reason", "decided_at"])


ai_matching_service = AIMatchingService()
