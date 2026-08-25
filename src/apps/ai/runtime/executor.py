"""Execute one persisted harness step with durable audit records."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.models import (
    AgentRun,
    AgentStep,
    AIRun,
    SourceArtifact,
    ToolInvocation,
)
from apps.ai.skills.registry import create_default_skill_registry
from apps.ai.tools.registry import create_default_tool_registry
from integrations.ai.gateway import ai_gateway

from .budget import Budget
from .state_machine import AgentStepStateMachine, StepTransition


@dataclass
class StepResult:
    step: AgentStep
    output: dict[str, Any] | None = None
    ai_run: AIRun | None = None
    tool_invocations: list[ToolInvocation] | None = None
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: Decimal | None = None
    latency_ms: int = 0


class StepExecutor:
    """Execute only explicitly implemented step kinds.

    A missing apply or approval handler is a hard failure, never a successful
    pass-through. This prevents incomplete workflows from claiming success.
    """

    def __init__(self, tool_registry=None, skill_registry=None) -> None:
        self._tool_registry = (
            create_default_tool_registry() if tool_registry is None else tool_registry
        )
        self._skill_registry = (
            create_default_skill_registry()
            if skill_registry is None
            else skill_registry
        )

    def execute(self, run: AgentRun, step: AgentStep, budget: Budget) -> StepResult:
        if run.status != AgentRun.Status.RUNNING:
            return StepResult(step=step, error=f"Run is {run.status}.")

        state = AgentStepStateMachine(step)
        if not state.transition(StepTransition.START):
            return StepResult(step=step, error=f"Step is {step.status}.")

        started = time.monotonic()
        try:
            if step.kind == AgentStep.Kind.MODEL:
                result = self._execute_model(run, step, budget)
            elif step.kind == AgentStep.Kind.TOOL:
                result = self._execute_tool(run, step)
            elif step.kind == AgentStep.Kind.PLAN:
                result = StepResult(step=step, output=step.input)
            else:
                result = StepResult(
                    step=step,
                    error=f"Step kind '{step.kind}' has no registered executor.",
                )
        except Exception as exc:  # persist failure before returning to Celery
            result = StepResult(step=step, error=f"{type(exc).__name__}: {exc}"[:4000])

        result.latency_ms = int((time.monotonic() - started) * 1000)
        self._finish_step(step, state, result)
        return result

    def _execute_model(
        self, run: AgentRun, step: AgentStep, budget: Budget
    ) -> StepResult:
        if budget.is_exhausted:
            return StepResult(
                step=step,
                error=f"Budget exhausted: {budget.exhaustion_reason}",
            )

        use_case = step.input.get("use_case", "entity_matching")
        system_prompt = step.input.get("system_prompt")
        payload = step.input.get("payload")
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            return StepResult(step=step, error="Model step requires system_prompt.")
        if not isinstance(payload, dict):
            return StepResult(step=step, error="Model step payload must be an object.")
        if not step.skill_name:
            return StepResult(
                step=step,
                error="Model steps require a versioned skill output contract.",
            )
        try:
            skill = self._skill_registry.get(step.skill_name)
        except KeyError as exc:
            return StepResult(step=step, error=str(exc))
        if step.skill_version and step.skill_version != skill.version:
            return StepResult(
                step=step,
                error=(
                    f"Skill version mismatch: step={step.skill_version}, "
                    f"registered={skill.version}."
                ),
            )
        try:
            skill.input_model.model_validate(payload)
        except Exception as exc:
            return StepResult(step=step, error=f"Invalid skill input: {exc}"[:4000])

        system_prompt = (
            f"{system_prompt.rstrip()}\nReturn JSON matching this schema exactly:\n"
            f"{json.dumps(skill.output_model.model_json_schema(), ensure_ascii=False)}"
        )

        started = timezone.now()
        model = ai_gateway.resolve_model(use_case)
        usage: dict[str, Any] = {}
        try:
            raw_output, usage = ai_gateway.complete_json(
                system_prompt=system_prompt,
                payload=payload,
                use_case=use_case,
            )
            output = skill.output_model.model_validate(raw_output).model_dump(
                mode="json"
            )
        except Exception as exc:
            input_tokens = _non_negative_int(usage.get("input_tokens"))
            output_tokens = _non_negative_int(usage.get("output_tokens"))
            cost = _non_negative_decimal(usage.get("cost"))
            AIRun.objects.create(
                agent_step=step,
                use_case=use_case,
                provider=ai_gateway.provider_name,
                model=str(usage.get("model") or model),
                prompt_version=step.skill_version or "harness-v1",
                input_hash=_hash_payload(payload),
                input_metadata={"step_id": str(step.pk)},
                status=AIRun.Status.FAILED,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                error=f"{type(exc).__name__}: {exc}"[:4000],
                started_at=started,
                finished_at=timezone.now(),
            )
            return StepResult(
                step=step,
                error=f"{type(exc).__name__}: {exc}",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
            )

        input_tokens = _non_negative_int(usage.get("input_tokens"))
        output_tokens = _non_negative_int(usage.get("output_tokens"))
        cost = _non_negative_decimal(usage.get("cost"))
        ai_run = AIRun.objects.create(
            agent_step=step,
            use_case=use_case,
            provider=ai_gateway.provider_name,
            model=str(usage.get("model") or model),
            prompt_version=step.skill_version or "harness-v1",
            input_hash=_hash_payload(payload),
            input_metadata={"step_id": str(step.pk)},
            output=output,
            status=AIRun.Status.SUCCEEDED,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            started_at=started,
            finished_at=timezone.now(),
        )
        return StepResult(
            step=step,
            output=output,
            ai_run=ai_run,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )

    def _execute_tool(self, run: AgentRun, step: AgentStep) -> StepResult:
        if self._tool_registry is None:
            return StepResult(step=step, error="No tool registry configured.")
        tool_name = step.input.get("tool_name")
        parameters = step.input.get("parameters", {})
        if not isinstance(tool_name, str) or not isinstance(parameters, dict):
            return StepResult(step=step, error="Tool step has invalid input.")

        tool = self._tool_registry.get(tool_name)
        granted_scopes = set(run.metadata.get("scopes", []))
        if tool.permission not in granted_scopes:
            return StepResult(
                step=step,
                error=f"Missing required scope '{tool.permission}'.",
            )
        idempotency_key = step.input.get("idempotency_key", "")
        idempotency_scope = run.idempotency_scope
        if (
            not isinstance(idempotency_key, str)
            or len(idempotency_key) > 128
            or not isinstance(idempotency_scope, str)
            or not idempotency_scope
            or len(idempotency_scope) > 128
        ):
            return StepResult(step=step, error="Tool idempotency metadata is invalid.")
        if tool.has_side_effects and not idempotency_key:
            return StepResult(
                step=step,
                error="Side-effecting tools require an idempotency key.",
            )
        if (
            tool.has_side_effects
            and parameters.get("idempotency_key") != idempotency_key
        ):
            return StepResult(
                step=step,
                error="Tool input must contain the same idempotency key as the step.",
            )
        previous = None
        if idempotency_key:
            previous = ToolInvocation.objects.filter(
                tool_name=tool.name,
                tool_version=tool.version,
                idempotency_key=idempotency_key,
                idempotency_scope=idempotency_scope,
            ).first()
            if (
                previous is not None
                and previous.status == ToolInvocation.Status.SUCCEEDED
            ):
                return StepResult(
                    step=step,
                    output=previous.result,
                    tool_invocations=[previous],
                )
            if (
                previous is not None
                and previous.status == ToolInvocation.Status.RUNNING
            ):
                return StepResult(
                    step=step, error="Tool invocation is already running."
                )
            if previous is not None and previous.status == ToolInvocation.Status.FAILED:
                return StepResult(
                    step=step,
                    error="Tool invocation previously failed; use a new idempotency key.",
                )
        if previous is None:
            invocation = ToolInvocation.objects.create(
                step=step,
                tool_name=tool.name,
                tool_version=tool.version,
                parameters=parameters,
                parameter_hash=_hash_payload(parameters),
                permission_scope=tool.permission,
                risk_level=tool.risk_level,
                has_side_effects=tool.has_side_effects,
                idempotency_key=idempotency_key,
                idempotency_scope=idempotency_scope,
            )
        else:
            return StepResult(step=step, error="Tool invocation cannot be reused.")
        try:
            result = tool.execute(parameters)
        except Exception as exc:
            invocation.status = ToolInvocation.Status.FAILED
            invocation.error = f"{type(exc).__name__}: {exc}"[:4000]
            invocation.finished_at = timezone.now()
            invocation.save(update_fields=["status", "error", "finished_at"])
            return StepResult(step=step, error=invocation.error)

        invocation.status = ToolInvocation.Status.SUCCEEDED
        invocation.result = result
        invocation.finished_at = timezone.now()
        invocation.save(update_fields=["status", "result", "finished_at"])
        if tool.records_evidence:
            encoded = json.dumps(
                result, sort_keys=True, ensure_ascii=False, default=str
            )
            encoded_bytes = encoded.encode()
            SourceArtifact.objects.create(
                tool_invocation=invocation,
                kind=SourceArtifact.Kind.INTERNAL_SNAPSHOT,
                content_hash=hashlib.sha256(encoded_bytes).hexdigest(),
                mime_type="application/json",
                byte_size=len(encoded_bytes),
                excerpt=encoded[:8000],
                metadata={"tool_name": tool.name, "tool_version": tool.version},
            )
        return StepResult(step=step, output=result, tool_invocations=[invocation])

    @staticmethod
    @transaction.atomic
    def _finish_step(
        step: AgentStep, state: AgentStepStateMachine, result: StepResult
    ) -> None:
        if not state.transition(
            StepTransition.FAIL if result.error else StepTransition.SUCCEED
        ):
            return
        AgentStep.objects.filter(pk=step.pk).update(
            output=result.output,
            error=result.error or "",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=result.cost,
            latency_ms=result.latency_ms,
        )


def _hash_payload(payload: dict[str, Any]) -> str:
    value = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
    ).encode()
    return hashlib.sha256(value).hexdigest()


def _non_negative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _non_negative_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None
