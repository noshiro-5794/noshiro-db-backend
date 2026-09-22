from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

import httpx
from django.conf import settings

from integrations.ai.exceptions import AIProviderError
from shared.outbound import httpx_client_kwargs


class ModelTier(StrEnum):
    """Budget tiers. Batch work stays on Fast; user intent uses Reasoning."""

    FAST = "AI_FAST_MODEL"
    REASONING = "AI_REASONING_MODEL"


# Every offline/batch decision path is explicitly pinned to the cheap tier.
USE_CASE_TIERS: dict[str, ModelTier] = {
    "entity_matching": ModelTier.FAST,
    "entity_classification": ModelTier.FAST,
    "bangumi_link_search": ModelTier.FAST,
    "evidence_extraction": ModelTier.FAST,
    "conflict_detection": ModelTier.FAST,
    "info_completion": ModelTier.FAST,
    "field_normalization": ModelTier.FAST,
    "schedule_completion": ModelTier.FAST,
    "agent_loop": ModelTier.FAST,
    "mal_recall": ModelTier.FAST,
    # Interactive user-facing agent work needs stronger intent/database
    # reasoning than batch classification.
    "knowledge_qa": ModelTier.REASONING,
    "user_agent": ModelTier.REASONING,
    "user_agent_loop": ModelTier.REASONING,
}


class OpenAICompatibleGateway:
    provider_name = "openai_compatible"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def resolve_model(self, use_case: str) -> str:
        tier = USE_CASE_TIERS.get(use_case, ModelTier.REASONING)
        return getattr(settings, tier.value)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            if settings.AI_AGENT_API_KEY:
                headers["Authorization"] = f"Bearer {settings.AI_AGENT_API_KEY}"
            self._client = httpx.Client(
                **httpx_client_kwargs(
                    headers=headers,
                    timeout=settings.AI_AGENT_TIMEOUT,
                )
            )
        return self._client

    def complete_json(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        use_case: str = "entity_matching",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not settings.AI_AGENT_API_KEY:
            raise AIProviderError("AI_AGENT_API_KEY is not configured.")
        model = self.resolve_model(use_case)
        result, usage = self._call(model, system_prompt, payload)
        return result, usage

    def complete_agent(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        use_case: str = "agent_loop",
    ) -> AgentCompletion:
        """Run one native tool-calling model turn over the given transcript."""
        if not settings.AI_AGENT_API_KEY:
            raise AIProviderError("AI_AGENT_API_KEY is not configured.")
        if not isinstance(messages, list) or not messages:
            raise AIProviderError("Agent transcript must contain at least one message.")
        request_payload: dict[str, Any] = {
            "model": self.resolve_model(use_case),
            "messages": messages,
            "temperature": 0,
        }
        if tools:
            request_payload["tools"] = tools
        try:
            response = self.client.post(
                settings.AI_AGENT_API_BASE_URL,
                json=request_payload,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            model = str(data.get("model") or request_payload["model"])
            usage = data.get("usage") or {}
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError(
                f"AI provider returned an invalid agent response: {exc}"
            ) from exc
        content = message.get("content") if isinstance(message, dict) else ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False) if content else ""
        return AgentCompletion(
            content=content,
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
            model=model,
            usage={
                "model": model,
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            },
        )

    @staticmethod
    def _confidence(result: dict[str, Any]) -> Decimal:
        try:
            raw = result.get("confidence")
            if raw is None or isinstance(raw, bool):
                return Decimal("0")
            return Decimal(str(raw))
        except Exception:
            return Decimal("0")

    def _call(
        self,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        request_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        try:
            response = self.client.post(
                settings.AI_AGENT_API_BASE_URL,
                json=request_payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError(
                f"AI provider returned an invalid response: {exc}"
            ) from exc
        if not isinstance(result, dict):
            raise AIProviderError("AI provider JSON output must be an object.")
        usage = data.get("usage") or {}
        return result, {
            "model": model,
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }


ai_gateway = OpenAICompatibleGateway()


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentCompletion:
    content: str
    model: str
    usage: dict[str, Any]
    tool_calls: list[AgentToolCall] = field(default_factory=list)


def _parse_tool_calls(raw: Any) -> list[AgentToolCall]:
    if not isinstance(raw, list):
        return []
    calls: list[AgentToolCall] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        call_id = str(item.get("id") or "")
        function = (
            item.get("function") if isinstance(item.get("function"), dict) else {}
        )
        name = str(function.get("name") or "")
        raw_arguments = function.get("arguments") or "{}"
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except (TypeError, ValueError):
                arguments = {}
        elif isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            arguments = {}
        if not call_id or not name or not isinstance(arguments, dict):
            continue
        calls.append(AgentToolCall(id=call_id, name=name, arguments=arguments))
    return calls
