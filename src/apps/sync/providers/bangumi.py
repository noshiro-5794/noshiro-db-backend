from typing import Any

import httpx
from django.conf import settings

from apps.index.models import Provider, ProviderRecord
from apps.sync.providers.contracts import (
    CatalogPage,
    CatalogSourceSpec,
    DeltaPage,
    SourceNamespaceSpec,
)
from apps.sync.providers.exceptions import BangumiAPIError
from apps.sync.providers.rate_limiter import DistributedRateLimiter
from shared.outbound import httpx_client_kwargs

BANGUMI_SOURCE = CatalogSourceSpec(
    slug="bangumi",
    name="Bangumi",
    base_url="https://bgm.tv",
    terms_url="https://bangumi.github.io/api/",
    attribution_url="https://bgm.tv",
)
BANGUMI_SUBJECT_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="subject",
    resource_type="subject",
    description="Bangumi subject",
)
BANGUMI_EPISODE_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="episode",
    resource_type="episode",
    description="Bangumi episode",
)
BANGUMI_PERSON_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="person",
    resource_type="person",
    description="Bangumi person, company, or group",
)
BANGUMI_CHARACTER_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="character",
    resource_type="character",
    description="Bangumi character",
)
BANGUMI_SUBJECT_RELATIONS_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="subject-relations",
    resource_type="collection",
    description="Point-in-time related-subject collection for a Bangumi subject",
)
BANGUMI_SUBJECT_STAFF_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="subject-staff",
    resource_type="collection",
    description="Point-in-time staff collection for a Bangumi subject",
)
BANGUMI_SUBJECT_CHARACTERS_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="subject-characters",
    resource_type="collection",
    description="Point-in-time character and voice cast collection for a subject",
)
BANGUMI_SUBJECT_EPISODES_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="subject-episodes",
    resource_type="collection",
    description="Point-in-time episode collection for a Bangumi subject",
)
BANGUMI_CALENDAR_NAMESPACE = SourceNamespaceSpec(
    source=BANGUMI_SOURCE,
    slug="calendar",
    resource_type="schedule",
    description="Point-in-time Bangumi weekly broadcast calendar",
)

# Bangumi's browse endpoint only accepts these subject types and skips type 5.
BANGUMI_SUBJECT_TYPES = (1, 2, 3, 4, 6)
# Offset paging beyond this bound is rejected by the API; treat it as terminal.
BANGUMI_BROWSE_MAX_OFFSET = 100_000


class BangumiClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._rate_limiter = DistributedRateLimiter(
            "bangumi",
            settings.BANGUMI_RATE_LIMIT_INTERVAL,
            allow_fallback=client is not None,
        )

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
            **httpx_client_kwargs(
                base_url=settings.BANGUMI_API_BASE_URL,
                headers=headers,
                timeout=settings.BANGUMI_TIMEOUT,
                follow_redirects=True,
            )
        )

    def _get(self, path: str, **kwargs: Any) -> Any:
        provider = (
            Provider.objects.filter(slug=BANGUMI_SOURCE.slug)
            .only("is_enabled", "storage_policy")
            .first()
        )
        if provider is not None:
            if not provider.is_enabled:
                raise BangumiAPIError("Bangumi provider is disabled.")
            if provider.storage_policy == Provider.UsagePolicy.FORBIDDEN:
                raise BangumiAPIError(
                    "Bangumi provider forbids source payload storage."
                )
        self._rate_limiter.acquire()
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

    def discover_subject_page(
        self,
        *,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> CatalogPage:
        """Page the browse endpoint across all subject types.

        ``GET /v0/subjects`` requires ``type`` and only supports date/rank
        sorting, so the cursor encodes ``<type>:<offset>``. The endpoint is an
        approximate catalog view rather than a stable global enumeration, so a
        full campaign cannot prove completeness (see docs/development.md).
        """
        type_id, offset = parse_bangumi_cursor(cursor)
        limit = min(max(page_size, 1), 100)
        payload = self._get(
            "/v0/subjects",
            params={
                "type": type_id,
                "limit": limit,
                "offset": offset,
                "sort": "date",
            },
        )
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            items = payload["data"]
            total_count = payload.get("total")
        elif isinstance(payload, list):
            # Older/unwrapped responses are tolerated for forward compatibility.
            items = payload
            total_count = None
        else:
            raise BangumiAPIError("Bangumi subjects response must contain a data list.")
        external_ids = tuple(
            str(item["id"])
            for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        )
        parsed_total = int(total_count) if isinstance(total_count, (int, str)) else None
        next_cursor: str | None
        if len(external_ids) == limit and offset + limit < BANGUMI_BROWSE_MAX_OFFSET:
            next_cursor = f"{type_id}:{offset + limit}"
        elif (next_type_index := BANGUMI_SUBJECT_TYPES.index(type_id) + 1) < len(
            BANGUMI_SUBJECT_TYPES
        ):
            next_cursor = f"{BANGUMI_SUBJECT_TYPES[next_type_index]}:0"
        else:
            next_cursor = None
        return CatalogPage(
            external_ids=external_ids,
            next_cursor=next_cursor,
            total_count=parsed_total,
        )

    def discover_subject_delta_page(
        self,
        *,
        watermark: str,
        cursor: str | None = None,
        page_size: int = 100,
    ) -> DeltaPage:
        """Re-fetch known records; new IDs are found by periodic frontier scans."""
        del watermark
        offset = max(0, int(cursor or "0"))
        limit = min(max(page_size, 1), 1000)
        records = ProviderRecord.objects.filter(
            namespace__provider__slug=BANGUMI_SOURCE.slug,
            namespace__slug=BANGUMI_SUBJECT_NAMESPACE.slug,
            status=ProviderRecord.Status.ACTIVE,
        ).order_by("external_id")
        external_ids = tuple(
            records.values_list("external_id", flat=True)[offset : offset + limit]
        )
        return DeltaPage(
            external_ids=external_ids,
            next_cursor=str(offset + limit) if len(external_ids) == limit else None,
            watermark="known-record-reconciliation",
            total_count=records.count(),
        )

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


def parse_bangumi_cursor(cursor: str | None) -> tuple[int, int]:
    """Parse ``<type>:<offset>`` with a safe fallback to the first subject type."""
    if cursor:
        raw = str(cursor).split(":", 1)
        try:
            type_id = int(raw[0])
            offset = int(raw[1]) if len(raw) == 2 else 0
            if type_id in BANGUMI_SUBJECT_TYPES and offset >= 0:
                return type_id, offset
        except ValueError:
            pass
    return BANGUMI_SUBJECT_TYPES[0], 0


bangumi_client = BangumiClient()
