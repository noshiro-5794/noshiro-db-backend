"""Durable orchestration for persisted harness runs.

The database is the source of truth for execution progress. Checkpoints are
auditable snapshots and are never used to recreate steps during resume.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AgentRun, AgentStep

from .budget import Budget, BudgetManager
from .checkpoint import CheckpointManager
from .executor import StepExecutor
from .state_machine import (
    AgentRunStateMachine,
    AgentStepStateMachine,
    RunTransition,
    StepTransition,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentOrchestrator:
    """Coordinate plan, execution, retry, checkpoint, and terminal state."""

    executor: StepExecutor = field(default_factory=StepExecutor)
    max_retries_per_step: int = 3

    @transaction.atomic
    def start(self, run: AgentRun) -> AgentRun:
        run = AgentRun.objects.select_for_update().get(pk=run.pk)
        if run.status == AgentRun.Status.QUEUED:
            AgentRunStateMachine(run).transition(RunTransition.START)
        elif run.status != AgentRun.Status.RUNNING:
            logger.warning("Cannot start run %s in status %s", run.pk, run.status)
        return run

    @transaction.atomic
    def plan(self, run: AgentRun, plan_input: dict[str, Any]) -> list[AgentStep]:
        """Persist a plan exactly once and return the durable step records."""
        existing = list(run.steps.order_by("sequence"))
        if existing:
            return existing

        raw_steps = plan_input.get("steps", [])
        if not isinstance(raw_steps, list):
            raise ValueError("Plan input 'steps' must be a list.")

        valid_kinds = {choice for choice, _label in AgentStep.Kind.choices}
        steps: list[AgentStep] = []
        for sequence, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                raise ValueError(f"Plan step {sequence} must be an object.")
            kind = item.get("kind", AgentStep.Kind.MODEL)
            if kind not in valid_kinds:
                raise ValueError(f"Unknown agent step kind: {kind}")
            input_data = item.get("input", {})
            if not isinstance(input_data, dict):
                raise ValueError(f"Plan step {sequence} input must be an object.")
            steps.append(
                AgentStep(
                    run=run,
                    sequence=sequence,
                    kind=kind,
                    skill_name=item.get("skill_name", ""),
                    skill_version=item.get("skill_version", ""),
                    input_hash=_hash_payload(input_data),
                    input=input_data,
                )
            )
        AgentStep.objects.bulk_create(steps)
        CheckpointManager.save(run)
        return list(run.steps.order_by("sequence"))

    def execute_step(self, run: AgentRun, step: AgentStep, budget: Budget) -> bool:
        """Execute one attempt and account for it exactly once."""
        result = self.executor.execute(run, step, budget)
        budget.record_execution(
            input_tokens=result.input_tokens or 0,
            output_tokens=result.output_tokens or 0,
            cost=result.cost,
        )
        BudgetManager.save(run, budget)
        CheckpointManager.save(run)
        if result.error:
            logger.error("Step %s failed: %s", step.pk, result.error)
            return False
        return True

    def run_loop(
        self, run: AgentRun, plan_input: dict[str, Any] | None = None
    ) -> AgentRun:
        """Run all non-terminal persisted steps, retrying failures safely."""
        run = AgentRun.objects.get(pk=run.pk)
        if run.status == AgentRun.Status.QUEUED:
            run = self.start(run)
        if run.status != AgentRun.Status.RUNNING:
            return run

        steps = list(run.steps.order_by("sequence"))
        if not steps and plan_input is not None:
            steps = self.plan(run, plan_input)
        if not steps:
            self._fail_run(run, "Run has no persisted steps.")
            return AgentRun.objects.get(pk=run.pk)

        budget = BudgetManager.load(run)
        for step in steps:
            step = AgentStep.objects.get(pk=step.pk)
            if step.status in {
                AgentStep.Status.SUCCEEDED,
                AgentStep.Status.SKIPPED,
                AgentStep.Status.CANCELLED,
            }:
                continue
            if step.status in {AgentStep.Status.RUNNING, AgentStep.Status.WAITING}:
                return AgentRun.objects.get(pk=run.pk)
            if budget.is_exhausted:
                self._fail_run(run, f"Budget exhausted: {budget.exhaustion_reason}")
                return AgentRun.objects.get(pk=run.pk)

            success = False
            while True:
                step = AgentStep.objects.get(pk=step.pk)
                if step.status == AgentStep.Status.FAILED:
                    if step.retry_count >= self.max_retries_per_step - 1:
                        break
                    if not AgentStepStateMachine(step).transition(StepTransition.RETRY):
                        break
                    AgentStep.objects.filter(pk=step.pk).update(
                        retry_count=step.retry_count + 1,
                        error="",
                        finished_at=None,
                        output=None,
                    )
                    step.refresh_from_db()
                success = self.execute_step(run, step, budget)
                if success:
                    break
                logger.warning(
                    "Step %s attempt %d/%d failed",
                    step.pk,
                    step.retry_count + 1,
                    self.max_retries_per_step,
                )
                persisted_status = AgentStep.objects.values_list(
                    "status", flat=True
                ).get(pk=step.pk)
                if persisted_status != AgentStep.Status.FAILED:
                    return AgentRun.objects.get(pk=run.pk)
                if budget.is_exhausted:
                    break

            if not success:
                self._fail_run(
                    run,
                    f"Step {step.pk} failed after {self.max_retries_per_step} attempts",
                )
                return AgentRun.objects.get(pk=run.pk)

        self._succeed_run(run)
        return AgentRun.objects.get(pk=run.pk)

    def resume(self, run: AgentRun) -> AgentRun:
        """Resume existing database steps after a paused run."""
        run = AgentRun.objects.get(pk=run.pk)
        if not CheckpointManager.can_resume(run):
            logger.warning("Cannot resume run %s", run.pk)
            return run
        if not AgentRunStateMachine(run).transition(RunTransition.RESUME):
            return AgentRun.objects.get(pk=run.pk)
        self._recover_inflight_steps(run)
        return self.run_loop(AgentRun.objects.get(pk=run.pk))

    def cancel(self, run: AgentRun) -> AgentRun:
        run = AgentRun.objects.get(pk=run.pk)
        if AgentRunStateMachine(run).can_cancel():
            AgentRunStateMachine(run).transition(RunTransition.CANCEL)
            CheckpointManager.save(run)
        return AgentRun.objects.get(pk=run.pk)

    def pause(self, run: AgentRun) -> AgentRun:
        """Pause a running run at a checkpoint boundary."""
        run = AgentRun.objects.get(pk=run.pk)
        if AgentRunStateMachine(run).transition(RunTransition.PAUSE):
            CheckpointManager.save(run)
        return AgentRun.objects.get(pk=run.pk)

    @staticmethod
    def _recover_inflight_steps(run: AgentRun) -> None:
        """Make steps abandoned by a worker retryable on resume/re-entry."""
        AgentStep.objects.filter(run=run, status=AgentStep.Status.RUNNING).update(
            status=AgentStep.Status.FAILED,
            error="Execution was interrupted before completion.",
            finished_at=timezone.now(),
        )

    @staticmethod
    def _succeed_run(run: AgentRun) -> None:
        AgentRunStateMachine(run).transition(RunTransition.SUCCEED)
        CheckpointManager.save(run)

    @staticmethod
    def _fail_run(run: AgentRun, error: str) -> None:
        if not AgentRunStateMachine(run).transition(RunTransition.FAIL):
            return
        AgentRun.objects.filter(pk=run.pk).update(error=error[:4000])
        CheckpointManager.save(run)


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
