from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AgentRun

DEFAULT_MAX_TOKENS = 200_000
DEFAULT_MAX_COST_USD = Decimal("5.00")
DEFAULT_MAX_STEPS = 100


@dataclass
class Budget:
    max_input_tokens: int = DEFAULT_MAX_TOKENS
    max_output_tokens: int = DEFAULT_MAX_TOKENS
    max_cost_usd: Decimal = field(default_factory=lambda: DEFAULT_MAX_COST_USD)
    max_steps: int = DEFAULT_MAX_STEPS

    input_tokens_used: int = 0
    output_tokens_used: int = 0
    cost_used: Decimal = Decimal("0")
    steps_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_usd": str(self.max_cost_usd),
            "max_steps": self.max_steps,
            "input_tokens_used": self.input_tokens_used,
            "output_tokens_used": self.output_tokens_used,
            "cost_used": str(self.cost_used),
            "steps_used": self.steps_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Budget:
        if data is None:
            return cls()
        return cls(
            max_input_tokens=data.get("max_input_tokens", DEFAULT_MAX_TOKENS),
            max_output_tokens=data.get("max_output_tokens", DEFAULT_MAX_TOKENS),
            max_cost_usd=Decimal(str(data.get("max_cost_usd", DEFAULT_MAX_COST_USD))),
            max_steps=data.get("max_steps", DEFAULT_MAX_STEPS),
            input_tokens_used=data.get("input_tokens_used", 0),
            output_tokens_used=data.get("output_tokens_used", 0),
            cost_used=Decimal(str(data.get("cost_used", "0"))),
            steps_used=data.get("steps_used", 0),
        )

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens_used += input_tokens
        self.output_tokens_used += output_tokens

    def record_cost(self, cost: Decimal) -> None:
        self.cost_used += cost

    def record_step(self) -> None:
        self.steps_used += 1

    def record_execution(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: Decimal | None = None,
    ) -> None:
        """Account one executor attempt, including retries and failures."""
        self.record_tokens(input_tokens, output_tokens)
        if cost is not None:
            self.record_cost(cost)
        self.record_step()

    @property
    def is_exhausted(self) -> bool:
        return (
            self.input_tokens_used >= self.max_input_tokens
            or self.output_tokens_used >= self.max_output_tokens
            or self.cost_used >= self.max_cost_usd
            or self.steps_used >= self.max_steps
        )

    @property
    def exhaustion_reason(self) -> str | None:
        if self.input_tokens_used >= self.max_input_tokens:
            return "input_token_budget_exhausted"
        if self.output_tokens_used >= self.max_output_tokens:
            return "output_token_budget_exhausted"
        if self.cost_used >= self.max_cost_usd:
            return "cost_budget_exhausted"
        if self.steps_used >= self.max_steps:
            return "step_budget_exhausted"
        return None


@dataclass
class BudgetManager:
    @staticmethod
    def load(run: AgentRun) -> Budget:
        return Budget.from_dict(run.budget)

    @staticmethod
    @transaction.atomic
    def save(run: AgentRun, budget: Budget) -> None:
        AgentRun.objects.filter(pk=run.pk).update(
            budget=budget.to_dict(),
            updated_at=timezone.now(),
        )
        run.budget = budget.to_dict()
