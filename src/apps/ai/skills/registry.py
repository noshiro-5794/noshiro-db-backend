"""Versioned Skill contracts.

Skills are deterministic application components that may request model
inference. They do not write canonical data directly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    version: str
    prompt_version: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[..., BaseModel]
    use_case: str
    mode: str = "shadow"
    model_preference: str = "fast"

    @property
    def content_hash(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version,
            "prompt_version": self.prompt_version,
            "input": self.input_model.model_json_schema(),
            "output": self.output_model.model_json_schema(),
        }
        value = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(value).hexdigest()


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' is already registered.")
        self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Skill '{name}' is not registered.") from exc

    def list_all(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def __contains__(self, name: str) -> bool:
        return name in self._skills


skill_registry = SkillRegistry()


def create_default_skill_registry() -> SkillRegistry:
    """Build the registry of shipped skills without import-time side effects."""
    from .field_normalization.handler import field_normalization_skill

    registry = SkillRegistry()
    registry.register(field_normalization_skill.definition)
    return registry
