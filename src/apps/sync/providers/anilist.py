from typing import Any

import httpx
from django.conf import settings

from apps.index.models import Provider, ProviderNamespace
from apps.sync.providers.contracts import (
    CatalogPage,
    CatalogSourceSpec,
    DeltaPage,
    SourceNamespaceSpec,
)
from apps.sync.providers.exceptions import AniListAPIError
from apps.sync.providers.rate_limiter import DistributedRateLimiter
from shared.outbound import httpx_client_kwargs

ANILIST_SOURCE = CatalogSourceSpec(
    slug="anilist",
    name="AniList",
    base_url="https://anilist.co",
    terms_url="https://anilist.gitbook.io/anilist-apiv2-docs/",
    attribution_url="https://anilist.co",
)
ANILIST_ANIME_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="anime",
    resource_type=ProviderNamespace.ResourceType.SUBJECT,
    description="AniList anime media",
)
ANILIST_EPISODE_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="episode",
    resource_type=ProviderNamespace.ResourceType.EPISODE,
    description="AniList airing schedule episode",
)
ANILIST_CALENDAR_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="calendar",
    resource_type=ProviderNamespace.ResourceType.SCHEDULE,
    description="Point-in-time AniList airing schedule for a media entry",
)
ANILIST_CHARACTER_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="character",
    resource_type=ProviderNamespace.ResourceType.CHARACTER,
    description="AniList character",
)
ANILIST_STAFF_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="staff",
    resource_type=ProviderNamespace.ResourceType.PERSON,
    description="AniList staff person",
)
ANILIST_STUDIO_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="studio",
    resource_type=ProviderNamespace.ResourceType.ORGANIZATION,
    description="AniList animation studio",
)
ANILIST_GENRE_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="genre",
    resource_type=ProviderNamespace.ResourceType.TAXONOMY,
    description="AniList genre",
)
ANILIST_TAG_NAMESPACE = SourceNamespaceSpec(
    source=ANILIST_SOURCE,
    slug="tag",
    resource_type=ProviderNamespace.ResourceType.TAXONOMY,
    description="AniList media tag",
)


class AniListClient:
    CATALOG_QUERY = """
    query ($page: Int!, $perPage: Int!) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { hasNextPage total }
        media(type: ANIME, sort: ID) { id }
      }
    }
    """
    DELTA_QUERY = """
    query ($page: Int!, $perPage: Int!, $updatedAfter: Int!) {
      Page(page: $page, perPage: $perPage) {
        pageInfo { hasNextPage }
        media(type: ANIME, sort: UPDATED_AT_DESC, updatedAt_greater: $updatedAfter) {
          id
          updatedAt
        }
      }
    }
    """
    MEDIA_QUERY = """
    query ($id: Int, $page: Int, $perPage: Int) {
      Media(id: $id, type: ANIME) {
        id
        idMal
        type
        format
        status
        description
        season
        seasonYear
        episodes
        duration
        source
        averageScore
        popularity
        favourites
        trending
        isAdult
        genres
        synonyms
        coverImage { extraLarge large medium color }
        bannerImage
        siteUrl
        updatedAt
        title { romaji english native userPreferred }
        startDate { year month day }
        endDate { year month day }
        nextAiringEpisode { airingAt timeUntilAiring episode }
        externalLinks { id url site type }
        studios { edges { isMain node { id name } } }
        staff { edges { role node { id name { full native } languageV2 image { large medium } } } }
        characters { edges { role node { id name { full native } image { large medium } } voiceActors { id name { full native } languageV2 image { large medium } } } }
        relations { edges { relationType node { id type title { romaji english native } } } }
        tags { id name rank category isMediaSpoiler }
        airingSchedule(page: $page, perPage: $perPage) {
          pageInfo { hasNextPage }
          nodes { id episode airingAt timeUntilAiring }
        }
      }
    }
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._rate_limiter = DistributedRateLimiter(
            "anilist",
            settings.ANILIST_RATE_LIMIT_INTERVAL,
            allow_fallback=client is not None,
        )

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                **httpx_client_kwargs(
                    base_url=settings.ANILIST_API_BASE_URL,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": settings.ANILIST_USER_AGENT,
                    },
                    timeout=settings.ANILIST_TIMEOUT,
                    follow_redirects=True,
                )
            )
        return self._client

    def _post(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        provider = (
            Provider.objects.filter(slug=ANILIST_SOURCE.slug)
            .only("is_enabled", "storage_policy")
            .first()
        )
        if provider is not None:
            if not provider.is_enabled:
                raise AniListAPIError("AniList provider is disabled.")
            if provider.storage_policy == Provider.UsagePolicy.FORBIDDEN:
                raise AniListAPIError(
                    "AniList provider forbids source payload storage."
                )

        self._rate_limiter.acquire()
        try:
            response = self.client.post(
                "", json={"query": query, "variables": variables}
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise AniListAPIError(
                f"AniList returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:500]}",
                status_code=exc.response.status_code,
                retry_after=_retry_after(exc.response),
            ) from exc
        except httpx.RequestError as exc:
            raise AniListAPIError(f"AniList request failed: {exc}") from exc
        except ValueError as exc:
            raise AniListAPIError("AniList returned invalid JSON.") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise AniListAPIError("AniList returned an invalid GraphQL response.")
        if errors := payload.get("errors"):
            detail = str(errors[0] if isinstance(errors, list) else errors)[:500]
            retryable = any(
                isinstance(error, dict)
                and error.get("extensions", {}).get("code")
                in {"RATE_LIMITED", "INTERNAL_SERVER_ERROR"}
                for error in (errors if isinstance(errors, list) else [errors])
            )
            error = AniListAPIError(f"AniList GraphQL error: {detail}")
            error.retryable = retryable
            raise error
        return payload["data"]

    def fetch_media(
        self,
        anilist_id: int,
        *,
        airing_page: int = 1,
        airing_per_page: int = 50,
    ) -> dict[str, Any]:
        data = self._post(
            self.MEDIA_QUERY,
            {"id": anilist_id, "page": airing_page, "perPage": airing_per_page},
        )
        media = data.get("Media")
        if not isinstance(media, dict):
            raise AniListAPIError(f"AniList media {anilist_id} was not found.")
        return media

    def discover_anime_page(
        self, *, cursor: str | None = None, page_size: int = 50
    ) -> CatalogPage:
        """Discover AniList anime IDs using the provider's cursor-like page API."""
        page = max(1, int(cursor or "1"))
        data = self._post(
            self.CATALOG_QUERY,
            {"page": page, "perPage": min(max(page_size, 1), 50)},
        )
        page_data = data.get("Page")
        if not isinstance(page_data, dict):
            raise AniListAPIError("AniList returned an invalid catalog page.")
        external_ids = tuple(
            str(item["id"])
            for item in page_data.get("media") or []
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        )
        page_info = page_data.get("pageInfo") or {}
        return CatalogPage(
            external_ids=external_ids,
            next_cursor=str(page + 1) if page_info.get("hasNextPage") else None,
            total_count=(
                int(page_info["total"])
                if isinstance(page_info.get("total"), int)
                else None
            ),
        )

    def discover_anime_delta_page(
        self,
        *,
        watermark: str,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> DeltaPage:
        try:
            updated_after = int(watermark)
        except (TypeError, ValueError) as exc:
            raise AniListAPIError(
                "AniList delta watermark must be a Unix timestamp."
            ) from exc
        page = max(1, int(cursor or "1"))
        data = self._post(
            self.DELTA_QUERY,
            {
                "page": page,
                "perPage": min(max(page_size, 1), 50),
                "updatedAfter": updated_after,
            },
        )
        page_data = data.get("Page")
        if not isinstance(page_data, dict):
            raise AniListAPIError("AniList returned an invalid delta page.")
        items = page_data.get("media") or []
        external_ids = tuple(
            str(item["id"])
            for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        )
        page_info = page_data.get("pageInfo") or {}
        return DeltaPage(
            external_ids=external_ids,
            next_cursor=str(page + 1) if page_info.get("hasNextPage") else None,
            watermark=str(updated_after),
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


anilist_client = AniListClient()


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
