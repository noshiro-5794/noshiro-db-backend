from typing import Any

import httpx
from django.conf import settings

from apps.index.models import Provider, ProviderNamespace
from apps.sync.providers.contracts import CatalogSourceSpec, SourceNamespaceSpec
from apps.sync.providers.exceptions import AniListAPIError
from apps.sync.providers.rate_limiter import RateLimiter
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
        self._rate_limiter = RateLimiter(settings.ANILIST_RATE_LIMIT_INTERVAL)

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
                f"{exc.response.text[:500]}"
            ) from exc
        except httpx.RequestError as exc:
            raise AniListAPIError(f"AniList request failed: {exc}") from exc
        except ValueError as exc:
            raise AniListAPIError("AniList returned invalid JSON.") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise AniListAPIError("AniList returned an invalid GraphQL response.")
        if errors := payload.get("errors"):
            detail = str(errors[0] if isinstance(errors, list) else errors)[:500]
            raise AniListAPIError(f"AniList GraphQL error: {detail}")
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

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


anilist_client = AniListClient()
