from typing import Any

import httpx
from django.conf import settings

from apps.sync.providers.rate_limiter import RateLimiter

rate_limiter = RateLimiter(interval=settings.BANGUMI_RATE_LIMIT_INTERVAL)


class BangumiAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_not_found(self) -> bool:
        return self.status_code == 404


class BangumiClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    @staticmethod
    def _build_client() -> httpx.Client:
        headers = {
            "Accept": "application/json",
            "User-Agent": settings.BANGUMI_USER_AGENT,
        }
        if settings.BANGUMI_API_KEY:
            headers["Authorization"] = f"Bearer {settings.BANGUMI_API_KEY}"
        return httpx.Client(
            base_url=settings.BANGUMI_API_BASE_URL,
            headers=headers,
            timeout=settings.BANGUMI_TIMEOUT,
            follow_redirects=True,
        )

    def _get(self, path: str, **kwargs: Any) -> Any:
        rate_limiter.acquire()
        try:
            response = self.client.get(path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise BangumiAPIError(
                f"Bangumi API returned {exc.response.status_code}: {detail}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise BangumiAPIError(f"Bangumi API request failed: {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BangumiAPIError("Bangumi API returned invalid JSON.") from exc

    def fetch_calendar(self) -> list[dict[str, Any]]:
        return self._get("/calendar")

    def fetch_subject(self, subject_id: int) -> dict[str, Any]:
        return self._get(f"/v0/subjects/{subject_id}")

    def fetch_subject_persons(self, subject_id: int) -> list[dict[str, Any]]:
        return self._get(f"/v0/subjects/{subject_id}/persons")

    def fetch_subject_characters(self, subject_id: int) -> list[dict[str, Any]]:
        return self._get(f"/v0/subjects/{subject_id}/characters")

    def fetch_subject_subjects(self, subject_id: int) -> list[dict[str, Any]]:
        return self._get(f"/v0/subjects/{subject_id}/subjects")

    def fetch_subject_episodes(
        self,
        subject_id: int,
        episode_type: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        params = {"subject_id": subject_id, "limit": limit, "offset": offset}
        if episode_type is not None:
            params["type"] = episode_type
        return self._get("/v0/episodes", params=params)

    def fetch_character(self, character_id: int) -> dict[str, Any]:
        return self._get(f"/v0/characters/{character_id}")

    def fetch_person(self, person_id: int) -> dict[str, Any]:
        return self._get(f"/v0/persons/{person_id}")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


bangumi_client = BangumiClient()
