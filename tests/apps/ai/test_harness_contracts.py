from decimal import Decimal

import pytest
from pydantic import Field

from apps.ai.models import AgentRun
from apps.ai.runtime.budget import Budget
from apps.ai.runtime.state_machine import AgentRunStateMachine, RunTransition
from apps.ai.tools.registry import (
    ToolDefinition,
    ToolInput,
    ToolOutput,
    create_default_tool_registry,
)
from apps.sync.models import SyncCampaign
from apps.sync.services.campaign_ai import SyncAIContext, sync_ai_service
from apps.sync.services.campaign_state import SyncCampaignStateMachine


class EchoInput(ToolInput):
    value: str = Field(min_length=1)


class EchoOutput(ToolOutput):
    value: str


def _echo(value: EchoInput) -> EchoOutput:
    return EchoOutput(value=value.value)


def test_typed_tool_rejects_extra_input_and_serializes_output() -> None:
    tool = ToolDefinition(
        name="test.echo",
        description="Echo a value.",
        input_model=EchoInput,
        output_model=EchoOutput,
        handler=_echo,
    )

    assert tool.execute({"value": "ok"}) == {"value": "ok"}
    with pytest.raises(ValueError, match="Invalid input"):
        tool.execute({"value": "ok", "unexpected": True})


def test_budget_records_one_execution_including_zero_usage() -> None:
    budget = Budget()
    budget.record_execution(cost=Decimal("0.010"))

    assert budget.steps_used == 1
    assert budget.input_tokens_used == 0
    assert budget.output_tokens_used == 0
    assert budget.cost_used == Decimal("0.010")


def test_invalid_run_transition_is_rejected_without_database_write() -> None:
    run = AgentRun(kind=AgentRun.Kind.USER_AGENT, status=AgentRun.Status.SUCCEEDED)

    assert not AgentRunStateMachine(run).transition(RunTransition.START)


def test_default_registry_exposes_namespaced_read_tools() -> None:
    registry = create_default_tool_registry()

    assert {tool.name for tool in registry.list_all()} == {
        "knowledge.search_entities",
        "knowledge.get_entity",
        "knowledge.get_relations",
    }


def test_sync_ai_off_mode_preserves_raw_value_without_a_database_run() -> None:
    campaign = SyncCampaign(
        provider_slug="vndb",
        campaign_type="full",
        ai_mode=SyncCampaign.AIMode.OFF,
    )
    context = SyncAIContext(campaign=campaign, entity=object())

    result = sync_ai_service.normalize_field(
        context=context,
        vocabulary="genre",
        source_text="  Original  ",
    )

    assert result.action == "preserve_raw"
    assert result.preferred_term == "Original"


def test_sync_campaign_rejects_invalid_phase_transition_without_write() -> None:
    campaign = SyncCampaign(
        provider_slug="vndb",
        campaign_type="full",
        status=SyncCampaign.Status.COMPLETED,
    )

    assert not SyncCampaignStateMachine(campaign).advance("fetching")
