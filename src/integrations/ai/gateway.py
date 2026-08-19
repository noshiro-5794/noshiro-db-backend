import json
from typing import Any

import httpx
from django.conf import settings

from integrations.ai.exceptions import AIProviderError
from shared.outbound import httpx_client_kwargs


class OpenAICompatibleGateway:
    provider_name = "openai_compatible"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def model_name(self) -> str:
        return settings.AI_AGENT_MODEL

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
        self, *, system_prompt: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, int | None]]:
        if not settings.AI_AGENT_API_KEY:
            raise AIProviderError("AI_AGENT_API_KEY is not configured.")
        request_payload = {
            "model": self.model_name,
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
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }


ai_gateway = OpenAICompatibleGateway()
