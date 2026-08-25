"""Safe knowledge tools reused by in-process skills and MCP transports."""

from typing import Any
from uuid import UUID

from pydantic import Field

from integrations.mcp.queries import (
    get_public_entity,
    get_public_relations,
    search_public_entities,
)

from .registry import ToolDefinition, ToolInput, ToolOutput, ToolRegistry


class SearchEntitiesInput(ToolInput):
    query: str = Field(default="", max_length=256)
    collection: str = Field(default="", max_length=64)
    language: str = Field(default="", max_length=35)
    limit: int = Field(default=20, ge=1, le=50)


class SearchEntitiesOutput(ToolOutput):
    results: list[dict[str, Any]]


class GetEntityInput(ToolInput):
    entity_id: UUID
    language: str = Field(default="", max_length=35)


class EntityOutput(ToolOutput):
    entity: dict[str, Any]


class RelationsOutput(ToolOutput):
    results: list[dict[str, Any]]


def _search_entities(value: SearchEntitiesInput) -> SearchEntitiesOutput:
    return SearchEntitiesOutput(
        **search_public_entities(
            query=value.query,
            collection=value.collection,
            language=value.language,
            limit=value.limit,
        )
    )


def _get_entity(value: GetEntityInput) -> EntityOutput:
    return EntityOutput(
        entity=get_public_entity(
            entity_id=value.entity_id,
            language=value.language,
        )
    )


def _get_relations(value: GetEntityInput) -> RelationsOutput:
    return RelationsOutput(
        **get_public_relations(
            entity_id=value.entity_id,
            language=value.language,
        )
    )


def register_knowledge_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="knowledge.search_entities",
            description="Search safe, public knowledge-base entity projections.",
            input_model=SearchEntitiesInput,
            output_model=SearchEntitiesOutput,
            handler=_search_entities,
            records_evidence=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="knowledge.get_entity",
            description="Get one safe, public entity projection.",
            input_model=GetEntityInput,
            output_model=EntityOutput,
            handler=_get_entity,
            records_evidence=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="knowledge.get_relations",
            description="Get safe, public relations for one entity.",
            input_model=GetEntityInput,
            output_model=RelationsOutput,
            handler=_get_relations,
            records_evidence=True,
        )
    )
