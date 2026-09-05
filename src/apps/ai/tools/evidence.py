"""Shared evidence capture for tool executions and direct skill calls."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.ai.models import SourceArtifact


def capture_artifact(
    *,
    payload: Any,
    kind: str,
    source_url: str = "",
    mime_type: str = "application/json",
    tool_name: str = "",
    tool_version: str = "",
    metadata: dict[str, Any] | None = None,
    tool_invocation=None,
) -> SourceArtifact:
    """Persist a content-addressed evidence artifact from a tool result."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    encoded = text.encode()
    return SourceArtifact.objects.create(
        tool_invocation=tool_invocation,
        kind=kind,
        source_url=source_url,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        mime_type=mime_type,
        byte_size=len(encoded),
        excerpt=text[:8000],
        metadata={
            **(metadata or {}),
            **({"tool_name": tool_name} if tool_name else {}),
            **({"tool_version": tool_version} if tool_version else {}),
        },
    )
