from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AgentRun, AgentStep

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages run checkpoints for pause/resume/replay."""

    @staticmethod
    def capture(run: AgentRun) -> dict[str, Any]:
        steps = list(
            AgentStep.objects.filter(run=run)
            .order_by("sequence")
            .values(
                "id",
                "sequence",
                "kind",
                "status",
                "parent_id",
                "skill_name",
                "skill_version",
                "input_hash",
                "input",
                "output",
                "error",
                "retry_count",
            )
        )
        checkpoint = {
            "run_id": str(run.pk),
            "run_status": run.status,
            "step_count": len(steps),
            "last_completed_sequence": max(
                (s["sequence"] for s in steps if s["status"] == "succeeded"),
                default=-1,
            ),
            "steps": _serialize_steps(steps),
            "captured_at": timezone.now().isoformat(),
        }
        checkpoint["content_hash"] = _hash_checkpoint(checkpoint)
        return checkpoint

    @staticmethod
    @transaction.atomic
    def save(run: AgentRun) -> None:
        checkpoint = CheckpointManager.capture(run)
        AgentRun.objects.filter(pk=run.pk).update(
            checkpoint=checkpoint,
            updated_at=timezone.now(),
        )
        run.checkpoint = checkpoint

    @staticmethod
    def can_resume(run: AgentRun) -> bool:
        return run.status == "paused" and bool(run.checkpoint)

    @staticmethod
    def replay_plan(run: AgentRun) -> list[dict[str, Any]]:
        """Return the list of steps that need re-execution after resume."""
        if not run.checkpoint:
            return []
        steps_data = run.checkpoint.get("steps", [])
        return [s for s in steps_data if s["status"] in ("queued", "running", "failed")]


def _serialize_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized = []
    for step in steps:
        serialized.append(
            {
                "id": str(step["id"]),
                "sequence": step["sequence"],
                "kind": step["kind"],
                "status": step["status"],
                "parent_id": str(step["parent_id"]) if step.get("parent_id") else None,
                "skill_name": step.get("skill_name", ""),
                "skill_version": step.get("skill_version", ""),
                "input_hash": step.get("input_hash", ""),
                "input": step.get("input") or {},
                "output": step.get("output"),
                "error": step.get("error", ""),
                "retry_count": step.get("retry_count", 0),
            }
        )
    return serialized


def _hash_checkpoint(checkpoint: dict[str, Any]) -> str:
    payload = json.dumps(
        checkpoint, sort_keys=True, ensure_ascii=False, default=str
    ).encode()
    return hashlib.sha256(payload).hexdigest()
