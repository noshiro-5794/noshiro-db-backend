"""Pydantic contracts for evidence-first entity enrichment."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WebEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    url: str = Field(default="", max_length=2048)
    content: str = Field(default="", max_length=2000)
    score: float | None = None


class InfoCompletionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1, max_length=64)
    provider: str = Field(min_length=1, max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    preferred_name: str = Field(default="", max_length=512)
    original_name: str = Field(default="", max_length=512)
    source_language: str = Field(default="", max_length=35)
    release_date: str = Field(default="", max_length=32)
    missing_fields: list[str] = Field(default_factory=list, max_length=16)
    existing_names: dict[str, str] = Field(default_factory=dict, max_length=32)
    context: dict[str, Any] = Field(default_factory=dict)
    web_evidence: list[WebEvidence] = Field(default_factory=list, max_length=10)


class FieldProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Literal["title", "description"]
    language: str = Field(min_length=2, max_length=35)
    script: str = Field(default="", max_length=8)
    text: str = Field(min_length=1, max_length=4000)
    kind: Literal["translated", "romanized", "official", "short"] = "translated"
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(default="", max_length=2000)
    source: Literal["model", "web"]


class InfoCompletionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["complete", "abstain"]
    proposals: list[FieldProposal] = Field(default_factory=list, max_length=16)
    summary: str = Field(default="", max_length=2000)
