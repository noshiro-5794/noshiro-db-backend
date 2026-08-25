from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from django.utils import timezone

from apps.ai.models import AgentRun, AgentStep

logger = logging.getLogger(__name__)


class RunTransition(Enum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    SUCCEED = "succeed"
    FAIL = "fail"
    CANCEL = "cancel"


class StepTransition(Enum):
    START = "start"
    RETRY = "retry"
    SUCCEED = "succeed"
    FAIL = "fail"
    SKIP = "skip"
    CANCEL = "cancel"


_RUN_TRANSITIONS: dict[tuple[str, RunTransition], str] = {
    ("queued", RunTransition.START): "running",
    ("running", RunTransition.PAUSE): "paused",
    ("running", RunTransition.SUCCEED): "succeeded",
    ("running", RunTransition.FAIL): "failed",
    ("running", RunTransition.CANCEL): "cancelled",
    ("paused", RunTransition.RESUME): "running",
    ("paused", RunTransition.CANCEL): "cancelled",
}

_STEP_TRANSITIONS: dict[tuple[str, StepTransition], str] = {
    ("queued", StepTransition.START): "running",
    ("failed", StepTransition.RETRY): "queued",
    ("running", StepTransition.SUCCEED): "succeeded",
    ("running", StepTransition.FAIL): "failed",
    ("running", StepTransition.SKIP): "skipped",
    ("queued", StepTransition.SKIP): "skipped",
    ("queued", StepTransition.CANCEL): "cancelled",
    ("running", StepTransition.CANCEL): "cancelled",
}


@dataclass
class AgentRunStateMachine:
    run: AgentRun

    def transition(self, action: RunTransition) -> bool:
        current_status = self.run.status
        new_status = _RUN_TRANSITIONS.get((current_status, action))
        if new_status is None:
            logger.warning(
                "Invalid run transition: %s -> %s", self.run.status, action.value
            )
            return False
        now = timezone.now()
        updates: dict[str, Any] = {"status": new_status, "updated_at": now}
        if action == RunTransition.START and self.run.started_at is None:
            updates["started_at"] = now
        if action in (RunTransition.SUCCEED, RunTransition.FAIL, RunTransition.CANCEL):
            updates["finished_at"] = now
        updated = AgentRun.objects.filter(pk=self.run.pk, status=current_status).update(
            **updates
        )
        if updated != 1:
            logger.warning("Concurrent run transition lost for %s", self.run.pk)
            return False
        self.run.status = new_status
        return True

    def can_start(self) -> bool:
        return (self.run.status, RunTransition.START) in _RUN_TRANSITIONS

    def can_cancel(self) -> bool:
        return (self.run.status, RunTransition.CANCEL) in _RUN_TRANSITIONS


@dataclass
class AgentStepStateMachine:
    step: AgentStep

    def transition(self, action: StepTransition) -> bool:
        current_status = self.step.status
        new_status = _STEP_TRANSITIONS.get((current_status, action))
        if new_status is None:
            logger.warning(
                "Invalid step transition: %s -> %s", self.step.status, action.value
            )
            return False
        now = timezone.now()
        updates: dict[str, Any] = {"status": new_status}
        if action == StepTransition.START and self.step.started_at is None:
            updates["started_at"] = now
        if action in (
            StepTransition.SUCCEED,
            StepTransition.FAIL,
            StepTransition.SKIP,
            StepTransition.CANCEL,
        ):
            updates["finished_at"] = now
        updated = AgentStep.objects.filter(
            pk=self.step.pk, status=current_status
        ).update(**updates)
        if updated != 1:
            logger.warning("Concurrent step transition lost for %s", self.step.pk)
            return False
        self.step.status = new_status
        return True
