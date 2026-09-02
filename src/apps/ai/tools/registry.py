"""Typed tool contracts shared by the harness runtime and MCP adapters."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolDefinition[InputModel: BaseModel, OutputModel: BaseModel]:
    name: str
    description: str
    input_model: type[InputModel]
    output_model: type[OutputModel]
    handler: Callable[[InputModel], OutputModel]
    version: str = "1.0.0"
    permission: str = "knowledge:read"
    risk_level: str = "read_only"
    idempotent: bool = True
    has_side_effects: bool = False
    records_evidence: bool = False
    timeout_seconds: int = 30
    rate_limit_per_minute: int = 60

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", self.name) is None:
            raise ValueError(f"Tool name '{self.name}' is not namespaced.")
        if self.has_side_effects and not self.idempotent:
            raise ValueError("Side-effecting harness tools must be idempotent.")
        if self.has_side_effects and "idempotency_key" not in self.input_schema.get(
            "properties", {}
        ):
            raise ValueError(
                "Side-effecting tool input must declare an idempotency_key field."
            )

    def validate_input(self, parameters: dict[str, Any]) -> InputModel:
        try:
            return self.input_model.model_validate(parameters)
        except ValidationError as exc:
            raise ValueError(f"Invalid input for tool '{self.name}': {exc}") from exc

    def execute(self, parameters: dict[str, Any]) -> dict[str, Any]:
        output = self.handler(self.validate_input(parameters))
        if not isinstance(output, self.output_model):
            raise TypeError(
                f"Tool '{self.name}' returned {type(output).__name__}; "
                f"expected {self.output_model.__name__}."
            )
        return output.model_dump(mode="json")

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    @property
    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()

    @property
    def content_hash(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version,
            "input": self.input_schema,
            "output": self.output_schema,
            "permission": self.permission,
            "risk_level": self.risk_level,
            "idempotent": self.idempotent,
            "has_side_effects": self.has_side_effects,
            "records_evidence": self.records_evidence,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition[Any, Any]] = {}

    def register(self, tool: ToolDefinition[Any, Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition[Any, Any]:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool '{name}' is not registered.") from exc

    def list_by_permission(self, permission: str) -> list[ToolDefinition[Any, Any]]:
        return [tool for tool in self._tools.values() if tool.permission == permission]

    def list_all(self) -> list[ToolDefinition[Any, Any]]:
        return list(self._tools.values())

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


def create_default_tool_registry() -> ToolRegistry:
    """Build a registry used by harness workers and MCP adapters."""
    from .knowledge import register_knowledge_tools
    from .web import register_web_tools

    registry = ToolRegistry()
    register_knowledge_tools(registry)
    register_web_tools(registry)
    return registry


tool_registry = ToolRegistry()


def bootstrap_default_tools() -> ToolRegistry:
    """Register the built-in tools exactly once in the process singleton."""
    if not tool_registry:
        from .knowledge import register_knowledge_tools
        from .web import register_web_tools

        register_knowledge_tools(tool_registry)
        register_web_tools(tool_registry)
    return tool_registry
