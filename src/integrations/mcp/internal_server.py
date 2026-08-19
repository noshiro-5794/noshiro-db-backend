import uuid
from decimal import Decimal
from typing import Any

from asgiref.sync import sync_to_async
from mcp.types import ToolAnnotations

from apps.ai.services import ai_proposal_service
from integrations.mcp.queries import (
    get_match_candidate as query_match_candidate,
)
from integrations.mcp.queries import search_public_entities
from integrations.mcp.server import FastMCP

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
PROPOSAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)


def create_internal_mcp_server() -> FastMCP:
    server = FastMCP(
        "Noshiro Internal Knowledge Harness",
        instructions=(
            "Read source-neutral safe projections and submit auditable proposals. "
            "No tool writes canonical knowledge or user data."
        ),
    )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def search_entities(
        query: str = "",
        collection: str = "",
        language: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search public safe entity projections."""
        return await sync_to_async(search_public_entities, thread_sensitive=True)(
            query=query,
            collection=collection,
            language=language,
            limit=limit,
        )

    @server.tool(annotations=READ_ONLY, structured_output=True)
    async def get_match_candidate(candidate_id: uuid.UUID) -> dict[str, Any]:
        """Read one match candidate and its safe evidence projection."""
        return await sync_to_async(query_match_candidate, thread_sensitive=True)(
            candidate_id
        )

    @server.tool(annotations=PROPOSAL_WRITE, structured_output=True)
    async def submit_proposal(
        candidate_id: uuid.UUID,
        decision: str,
        confidence: Decimal,
        reason: str,
        prompt_version: str = "internal-mcp-v1",
    ) -> dict[str, Any]:
        """Submit an auditable proposal without changing canonical entities."""
        proposal = await sync_to_async(
            ai_proposal_service.submit,
            thread_sensitive=True,
        )(
            candidate_id=candidate_id,
            decision=decision,
            confidence=confidence,
            reason=reason,
            prompt_version=prompt_version,
            input_metadata={"transport": "stdio"},
        )
        return {
            "proposal_id": str(proposal.id),
            "status": proposal.status,
            "canonical_write": False,
        }

    return server
