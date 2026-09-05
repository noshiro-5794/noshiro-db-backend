import json
from decimal import Decimal
from typing import Any

import httpx
from django.conf import settings

from integrations.ai.exceptions import AIProviderError
from shared.outbound import httpx_client_kwargs

_MODEL_ROUTING: dict[str, str] = {
    "entity_matching": "AI_REASONING_MODEL",
    "entity_classification": "AI_FAST_MODEL",
    "evidence_extraction": "AI_FAST_MODEL",
    "conflict_detection": "AI_REASONING_MODEL",
    "info_completion": "AI_FAST_MODEL",
    "field_normalization": "AI_FAST_MODEL",
    "knowledge_qa": "AI_FAST_MODEL",
    "user_agent": "AI_FAST_MODEL",
}

_CLASSIFICATION_FALLBACK_THRESHOLD = Decimal("0.85")


class OpenAICompatibleGateway:
    provider_name = "openai_compatible"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def resolve_model(self, use_case: str) -> str:
        setting_key = _MODEL_ROUTING.get(use_case, "AI_PRIMARY_MODEL")
        return getattr(settings, setting_key)

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
        if (
            use_case == "entity_classification"
            and model == settings.AI_FAST_MODEL
            and self._confidence(result) < _CLASSIFICATION_FALLBACK_THRESHOLD
        ):
            result, usage = self._call(
                settings.AI_PRIMARY_MODEL, system_prompt, payload
            )
        return result, usage

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
