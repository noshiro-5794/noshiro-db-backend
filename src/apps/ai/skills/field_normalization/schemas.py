"""Pydantic contracts for field normalization."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FieldNormalizationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vocabulary: str = Field(min_length=1, max_length=64)
    source_text: str = Field(min_length=1, max_length=256)
    provider_namespace: str = Field(default="", max_length=128)
    language: str = Field(default="", max_length=35)
    context: dict[str, Any] = Field(default_factory=dict)


class ProposedLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(min_length=1, max_length=35)
    script: str = Field(default="", max_length=8)
    text: str = Field(min_length=1, max_length=256)
    is_preferred: bool = False


class FieldNormalizationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["map_existing", "propose_new", "preserve_raw", "abstain"]
    normalized_key: str = Field(default="", max_length=256)
    preferred_term: str = Field(default="", max_length=256)
    language: str = Field(default="", max_length=35)
    script: str = Field(default="", max_length=8)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    existing_term_slug: str = Field(default="", max_length=128)
    proposed_labels: list[ProposedLabel] = Field(default_factory=list, max_length=16)
    source: Literal["alias", "model", "raw", "abstain"]
