import asyncio
import uuid
from unittest.mock import patch

import httpx
import pytest
from django.test import override_settings
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.types import LATEST_PROTOCOL_VERSION
from rest_framework_simplejwt.tokens import RefreshToken

from apps.ai.models import AIProposal, AIRun
from apps.index.models import Entity, EntityName, MatchCandidate, MatchDecision
from apps.users.models import User
from integrations.mcp.auth import NoshiroJWTTokenVerifier
from integrations.mcp.external_server import create_external_mcp_server
from integrations.mcp.internal_server import create_internal_mcp_server
from integrations.mcp.queries import get_public_entity, search_public_entities

pytestmark = pytest.mark.django_db(transaction=True)


def _tool_names(server: FastMCP) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_internal_and_external_servers_have_isolated_tool_allowlists() -> None:
    internal = create_internal_mcp_server()
    external = create_external_mcp_server()

    assert _tool_names(internal) == {
        "get_match_candidate",
        "search_entities",
        "submit_proposal",
    }
    assert _tool_names(external) == {
        "get_entity",
        "get_entity_relations",
        "search_entities",
    }


def test_internal_submit_proposal_is_audited_without_canonical_decision() -> None:
    left = Entity.objects.create(kind=Entity.Kind.WORK)
    right = Entity.objects.create(kind=Entity.Kind.WORK)
    candidate = MatchCandidate.objects.create(
        left_entity=left,
        right_entity=right,
        score="0.9990",
        runner_up_margin="0.1000",
        policy_version="match-v1",
    )
    server = create_internal_mcp_server()

    _content, result = asyncio.run(
        server.call_tool(
            "submit_proposal",
            {
                "candidate_id": str(candidate.id),
                "decision": "bind",
                "confidence": "0.9990",
                "reason": "Two independent evidence types agree.",
            },
        )
    )

    proposal = AIProposal.objects.get()
    candidate.refresh_from_db()
    assert proposal.run.provider == "internal_mcp"
    assert proposal.status == AIProposal.Status.PENDING
    assert candidate.status == MatchCandidate.Status.PENDING
    assert MatchDecision.objects.count() == 0
    assert AIRun.objects.count() == 1
    assert result["canonical_write"] is False


def test_public_mcp_token_verifier_accepts_only_active_access_tokens() -> None:
    user = User.objects.create_user(email="mcp@example.com")
    refresh = RefreshToken.for_user(user)
    verifier = NoshiroJWTTokenVerifier()

    access_info = asyncio.run(verifier.verify_token(str(refresh.access_token)))
    refresh_info = asyncio.run(verifier.verify_token(str(refresh)))
    invalid_info = asyncio.run(verifier.verify_token("not-a-token"))

    assert access_info is not None
    assert access_info.subject == str(user.id)
    assert access_info.scopes == ["knowledge:read"]
    assert refresh_info is None
    assert invalid_info is None

    user.is_active = False
    user.save(update_fields=["is_active"])
    assert asyncio.run(verifier.verify_token(str(refresh.access_token))) is None


def test_public_mcp_rejects_invalid_user_id_claim() -> None:
    token = RefreshToken.for_user(User.objects.create_user(email="claim@example.com"))
    malformed_access = token.access_token
    malformed_access["user_id"] = str(uuid.uuid4())

    assert (
        asyncio.run(NoshiroJWTTokenVerifier().verify_token(str(malformed_access)))
        is None
    )


def test_public_queries_never_return_restricted_entities() -> None:
    public = Entity.objects.create(kind=Entity.Kind.WORK)
    restricted = Entity.objects.create(
        kind=Entity.Kind.WORK,
        visibility=Entity.Visibility.RESTRICTED,
    )
    EntityName.objects.create(
        entity=public,
        text="Visible title",
        kind=EntityName.Kind.ORIGINAL,
    )
    EntityName.objects.create(
        entity=restricted,
        text="Restricted title",
        kind=EntityName.Kind.ORIGINAL,
    )

    results = search_public_entities(query="title", limit=50)["results"]

    assert [item["id"] for item in results] == [str(public.id)]
    with pytest.raises(ValueError, match="Public entity not found"):
        get_public_entity(entity_id=restricted.id)


@override_settings(MCP_RATE_LIMIT=1, MCP_RATE_WINDOW_SECONDS=60)
def test_external_tools_enforce_rate_limit_before_query() -> None:
    server = create_external_mcp_server()
    access_token = type(
        "Access",
        (),
        {"subject": str(uuid.uuid4())},
    )()

    with patch(
        "integrations.mcp.external_server.get_access_token",
        return_value=access_token,
    ):
        asyncio.run(server.call_tool("search_entities", {"limit": 1}))
        with pytest.raises(Exception, match="rate limit exceeded"):
            asyncio.run(server.call_tool("search_entities", {"limit": 1}))


def test_public_streamable_http_authentication_and_safe_projection() -> None:
    user = User.objects.create_user(email="transport@example.com")
    tokens = RefreshToken.for_user(user)
    visible = Entity.objects.create(kind=Entity.Kind.WORK)
    restricted = Entity.objects.create(
        kind=Entity.Kind.WORK,
        visibility=Entity.Visibility.RESTRICTED,
    )
    EntityName.objects.create(
        entity=visible,
        text="Transport visible",
        kind=EntityName.Kind.ORIGINAL,
    )
    EntityName.objects.create(
        entity=restricted,
        text="Transport restricted",
        kind=EntityName.Kind.ORIGINAL,
    )

    async def exercise_transport() -> None:
        server = create_external_mcp_server()
        app = server.streamable_http_app()
        initialize_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "noshiro-test", "version": "1"},
            },
        }
        transport = httpx.ASGITransport(app=app)

        async with server.session_manager.run():
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://127.0.0.1:8010",
            ) as anonymous_client:
                no_token = await anonymous_client.post(
                    "/mcp",
                    json=initialize_request,
                )
                refresh_token = await anonymous_client.post(
                    "/mcp",
                    json=initialize_request,
                    headers={"Authorization": f"Bearer {tokens}"},
                )

            assert no_token.status_code == 401
            assert no_token.json()["error"] == "invalid_token"
            assert refresh_token.status_code == 401

            async with (
                httpx.AsyncClient(
                    transport=transport,
                    base_url="http://127.0.0.1:8010",
                    headers={"Authorization": f"Bearer {tokens.access_token}"},
                ) as authenticated_client,
                streamable_http_client(
                    "http://127.0.0.1:8010/mcp",
                    http_client=authenticated_client,
                    terminate_on_close=False,
                ) as (read_stream, write_stream, _session_id),
                ClientSession(read_stream, write_stream) as session,
            ):
                initialized = await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool(
                    "search_entities",
                    {"query": "Transport", "limit": 50},
                )

            assert initialized.protocolVersion == LATEST_PROTOCOL_VERSION
            assert {tool.name for tool in tools.tools} == {
                "get_entity",
                "get_entity_relations",
                "search_entities",
            }
            assert result.isError is False
            assert [item["id"] for item in result.structuredContent["results"]] == [
                str(visible.id)
            ]

    asyncio.run(exercise_transport())


def test_internal_search_entities_returns_safe_projection() -> None:
    from apps.index.models import Entity, EntityName

    public = Entity.objects.create(kind=Entity.Kind.WORK)
    restricted = Entity.objects.create(
        kind=Entity.Kind.WORK,
        visibility=Entity.Visibility.RESTRICTED,
    )
    EntityName.objects.create(
        entity=public,
        text="Searchable",
        kind=EntityName.Kind.ORIGINAL,
    )
    EntityName.objects.create(
        entity=restricted,
        text="Hidden",
        kind=EntityName.Kind.ORIGINAL,
    )
    server = create_internal_mcp_server()

    _content, result = asyncio.run(
        server.call_tool("search_entities", {"query": "Searchable", "limit": 50})
    )
    assert [item["id"] for item in result["results"]] == [str(public.id)]


def test_internal_get_match_candidate_returns_evidence() -> None:
    from apps.index.models import Entity, MatchCandidate

    left = Entity.objects.create(kind=Entity.Kind.WORK)
    right = Entity.objects.create(kind=Entity.Kind.WORK)
    candidate = MatchCandidate.objects.create(
        left_entity=left,
        right_entity=right,
        score="0.9990",
        runner_up_margin="0.1000",
        policy_version="match-v1",
    )
    server = create_internal_mcp_server()

    _content, result = asyncio.run(
        server.call_tool("get_match_candidate", {"candidate_id": str(candidate.id)})
    )
    assert result["id"] == str(candidate.id)


def test_get_public_entity_raises_for_nonexistent_id() -> None:
    import uuid

    with pytest.raises(ValueError, match="Public entity not found"):
        get_public_entity(entity_id=uuid.uuid4())


def test_get_match_candidate_raises_for_nonexistent_id() -> None:
    import uuid

    from integrations.mcp.queries import get_match_candidate

    with pytest.raises(ValueError, match="Match candidate not found"):
        get_match_candidate(candidate_id=uuid.uuid4())


def test_get_public_relations_skips_non_public_and_duplicates() -> None:
    from apps.index.models import Entity, EntityName, EntityRelation
    from integrations.mcp.queries import get_public_relations

    public = Entity.objects.create(kind=Entity.Kind.WORK)
    restricted = Entity.objects.create(
        kind=Entity.Kind.WORK,
        visibility=Entity.Visibility.RESTRICTED,
    )
    EntityName.objects.create(
        entity=public, text="Public", kind=EntityName.Kind.ORIGINAL
    )
    EntityName.objects.create(
        entity=restricted, text="Hidden", kind=EntityName.Kind.ORIGINAL
    )

    EntityRelation.objects.create(
        from_entity=public,
        to_entity=restricted,
        relation_type="related",
    )
    result = get_public_relations(entity_id=public.id)
    assert result["results"] == []
