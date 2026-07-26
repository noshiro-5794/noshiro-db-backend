from typing import Any

import httpx
from django.conf import settings


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider cannot return a usable response."""


class AIClient:
    NAME_SYSTEM_PROMPT = """
You are an anime metadata normalization system.

Your task is to normalize any tag, role, format, or concept into ONE canonical Japanese word used in anime databases.

Rules:

1 Output ONLY ONE Japanese word.
2 No explanations.
3 No punctuation.
4 No extra text.
5 If the input is already Japanese, normalize it.
6 Understand Chinese, English and Japanese (include Romaji).
7 Convert synonyms to the standard anime term.

Examples:

校园 -> 学園
school -> 学園

TV -> TV
tv anime -> TV

游戏 -> ゲーム
game -> ゲーム
ゲーム -> ゲーム

监督 -> 監督
director -> 監督

seiyuu -> 声優
voice actor -> 声優
    """.strip()

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    @staticmethod
    def _build_client() -> httpx.Client:
        headers = {"Content-Type": "application/json"}
        if settings.AI_AGENT_API_KEY:
            headers["Authorization"] = f"Bearer {settings.AI_AGENT_API_KEY}"
        return httpx.Client(
            headers=headers,
            timeout=settings.AI_AGENT_TIMEOUT,
        )

    def _request(self, messages: list[dict[str, str]]) -> str:
        if not settings.AI_AGENT_API_KEY:
            raise RuntimeError("AI_AGENT_API_KEY is not configured.")
        payload: dict[str, Any] = {
            "model": settings.AI_AGENT_MODEL,
            "messages": messages,
        }
        try:
            response = self.client.post(settings.AI_AGENT_API_BASE_URL, json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise AIProviderError(
                f"AI Agent API returned {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise AIProviderError(f"AI Agent API request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise AIProviderError("AI Agent API returned invalid JSON.") from exc
        try:
            result = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("AI Agent API response is missing content.") from exc
        if not isinstance(result, str) or not result.strip():
            raise AIProviderError("AI Agent API returned empty content.")
        return result.strip()

    def normalize_name(self, name: str) -> str:
        messages = [
            {"role": "system", "content": self.NAME_SYSTEM_PROMPT},
            {"role": "user", "content": name},
        ]
        return self._request(messages)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


ai_client = AIClient()
