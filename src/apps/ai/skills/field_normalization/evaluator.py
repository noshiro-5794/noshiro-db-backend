"""Small deterministic evaluator for field-normalization regression cases."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.ai.models import AIEvaluationRun

from .handler import FieldNormalizationSkill
from .schemas import FieldNormalizationInput


@dataclass(frozen=True)
class EvalCase:
    vocabulary: str
    source_text: str
    expected_action: str
    expected_term: str = ""
    provider_namespace: str = ""
    language: str = ""


@dataclass
class EvalResult:
    total: int = 0
    correct_action: int = 0
    correct_term: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def action_accuracy(self) -> float:
        return self.correct_action / self.total if self.total else 0

    @property
    def term_accuracy(self) -> float:
        return self.correct_term / self.total if self.total else 0


class FieldNormalizationEvaluator:
    def __init__(self, skill: FieldNormalizationSkill | None = None) -> None:
        self.skill = skill or FieldNormalizationSkill()

    def evaluate(self, dataset: list[EvalCase]) -> EvalResult:
        result = EvalResult(total=len(dataset))
        for case in dataset:
            output = self.skill.normalize(
                FieldNormalizationInput(
                    vocabulary=case.vocabulary,
                    source_text=case.source_text,
                    provider_namespace=case.provider_namespace,
                    language=case.language,
                )
            )
            if output.action == case.expected_action:
                result.correct_action += 1
            if case.expected_term and output.preferred_term == case.expected_term:
                result.correct_term += 1
            if output.action != case.expected_action:
                result.failures.append(
                    {"case": case.__dict__, "output": output.model_dump()}
                )
        return result

    @transaction.atomic
    def record_evaluation(
        self,
        result: EvalResult,
        *,
        policy_version: str = "field-normalization-v1",
        dataset_version: str = "v1",
    ) -> AIEvaluationRun:
        precision = Decimal(str(result.action_accuracy))
        recall = Decimal(str(result.term_accuracy))
        return AIEvaluationRun.objects.create(
            use_case="field_normalization",
            policy_version=policy_version,
            dataset_version=dataset_version,
            sample_count=result.total,
            precision=precision,
            recall=recall,
            metrics={
                "action_accuracy": result.action_accuracy,
                "term_accuracy": result.term_accuracy,
                "failure_count": len(result.failures),
            },
            passed=precision >= Decimal("0.95") and recall >= Decimal("0.90"),
        )
