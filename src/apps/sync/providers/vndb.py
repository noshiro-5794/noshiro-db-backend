from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings

from apps.index.models import Provider, ProviderNamespace
from apps.sync.providers.contracts import (
    CatalogPage,
    CatalogSourceSpec,
    SourceNamespaceSpec,
)
from apps.sync.providers.exceptions import VNDBAPIError
from shared.outbound import httpx_client_kwargs

VNDB_SOURCE = CatalogSourceSpec(
    slug="vndb",
    name="VNDB",
    base_url="https://api.vndb.org/kana",
    terms_url="https://api.vndb.org/kana",
    attribution_url="https://vndb.org",
    license_name="ODbL",
)
VNDB_VN_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="vn",
    resource_type=ProviderNamespace.ResourceType.SUBJECT,
)
VNDB_RELATED_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="vn-related",
    resource_type=ProviderNamespace.ResourceType.COLLECTION,
    description="Point-in-time result of VNDB records related to a visual novel",
)
VNDB_RELEASE_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="release",
    resource_type=ProviderNamespace.ResourceType.RELEASE,
)
VNDB_CHARACTER_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="character",
    resource_type=ProviderNamespace.ResourceType.CHARACTER,
)
VNDB_STAFF_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="staff",
    resource_type=ProviderNamespace.ResourceType.PERSON,
)
VNDB_STAFF_ALIAS_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="staff-alias",
    resource_type=ProviderNamespace.ResourceType.PERSON,
)
VNDB_PRODUCER_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="producer",
    resource_type=ProviderNamespace.ResourceType.ORGANIZATION,
)
VNDB_TAG_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="tag",
    resource_type=ProviderNamespace.ResourceType.TAXONOMY,
)
VNDB_TRAIT_NAMESPACE = SourceNamespaceSpec(
    source=VNDB_SOURCE,
    slug="trait",
    resource_type=ProviderNamespace.ResourceType.TAXONOMY,
)


@dataclass(frozen=True, slots=True)
class VNDBImportBatch:
    work: dict[str, Any]
    releases: tuple[dict[str, Any], ...] = ()
    characters: tuple[dict[str, Any], ...] = ()
    contributors: tuple[dict[str, Any], ...] = ()
    related_fetched: bool = False


class VNDBClient:
    VN_FIELDS = (
        "id,title,alttitle,aliases,released,languages,platforms,olang,description,"
        "length_minutes,length_votes,devstatus,popularity,rating,votecount,"
        "titles.lang,titles.title,titles.latin,titles.official,titles.main,"
        "image.url,image.sexual,image.violence,screenshots.url,screenshots.sexual,"
        "screenshots.violence,screenshots.release.id,developers.id,developers.name,"
        "developers.original,developers.type,developers.extlinks.url,"
        "developers.extlinks.label,tags.id,tags.name,tags.rating,tags.spoiler,"
        "tags.lie,relations.id,relations.title,relations.alttitle,relations.olang,"
        "relations.relation,relations.relation_official,staff.id,staff.aid,"
        "staff.name,staff.original,staff.lang,staff.role,staff.note,"
        "va.staff.id,va.staff.aid,va.staff.name,va.staff.original,va.staff.lang,"
        "va.character.id,va.character.name,va.character.original,va.note,"
        "extlinks.url,extlinks.label"
    )
    RELEASE_FIELDS = (
        "id,title,alttitle,released,languages.lang,languages.title,languages.latin,"
        "languages.main,languages.mtl,platforms,media.medium,media.qty,resolution,voiced,"
        "engine,official,patch,freeware,uncensored,minage,vns.id,vns.title,vns.rtype,"
        "producers.id,producers.name,producers.original,producers.type,"
        "producers.developer,producers.publisher,producers.extlinks.url,"
        "producers.extlinks.label,extlinks.url,extlinks.label"
    )
    CHARACTER_FIELDS = (
        "id,name,original,aliases,description,image.url,image.sexual,image.violence,"
        "sex,gender,blood_type,height,weight,bust,waist,hips,cup,birthday,age,"
        "vns.id,vns.role,vns.spoiler,vns.release.id,traits.id,traits.name,"
        "traits.group_id,traits.group_name,traits.spoiler,traits.lie"
    )
    STAFF_FIELDS = (
        "id,aid,ismain,name,original,lang,description,gender,aliases.aid,"
        "aliases.name,aliases.latin,aliases.ismain,extlinks.url,extlinks.label"
    )

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                **httpx_client_kwargs(
                    base_url=settings.VNDB_API_BASE_URL,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": settings.VNDB_USER_AGENT,
                    },
                    timeout=settings.VNDB_TIMEOUT,
                    follow_redirects=True,
                )
            )
        return self._client

    def query(
        self,
        endpoint: str,
        *,
        filters: list,
        fields: str,
        page: int = 1,
        results: int = 100,
        count: bool = False,
    ) -> dict[str, Any]:
        provider = (
            Provider.objects.filter(slug=VNDB_SOURCE.slug)
            .only("is_enabled", "storage_policy")
            .first()
        )
        if provider is not None:
            if not provider.is_enabled:
                raise VNDBAPIError("VNDB provider is disabled.")
            if provider.storage_policy == Provider.UsagePolicy.FORBIDDEN:
                raise VNDBAPIError("VNDB provider forbids source payload storage.")
        payload = {
            "filters": filters,
            "fields": fields,
            "page": page,
            "results": min(max(results, 1), 100),
            "count": count,
        }
        try:
            response = self.client.post(f"/{endpoint}", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise VNDBAPIError(
                f"VNDB {endpoint} returned {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise VNDBAPIError(f"VNDB {endpoint} request failed: {exc}") from exc
        except ValueError as exc:
            raise VNDBAPIError(f"VNDB {endpoint} returned invalid JSON.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise VNDBAPIError(f"VNDB {endpoint} returned an invalid response.")
        return data

    def fetch_vn(self, vndb_id: str) -> dict[str, Any]:
        data = self.query(
            "vn",
            filters=["id", "=", vndb_id],
            fields=self.VN_FIELDS,
            results=1,
        )
        if not data["results"]:
            raise VNDBAPIError(f"VNDB work {vndb_id} was not found.")
        return data["results"][0]

    def discover_vn_page(
        self, *, cursor: str | None = None, page_size: int = 100
    ) -> CatalogPage:
        """Discover stable VNDB work IDs without fetching canonical payloads."""
        page = max(1, int(cursor or "1"))
        data = self.query(
            "vn",
            filters=[],
            fields="id",
            page=page,
            results=page_size,
            count=True,
        )
        external_ids = tuple(
            item["id"]
            for item in data["results"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        return CatalogPage(
            external_ids=external_ids,
            next_cursor=str(page + 1) if data.get("more") else None,
            total_count=(
                int(data["count"]) if isinstance(data.get("count"), int) else None
            ),
        )

    def fetch_related(self, endpoint: str, *, vndb_id: str, fields: str) -> list[dict]:
        page = 1
        items: list[dict] = []
        while True:
            filters: list = ["vn", "=", ["id", "=", vndb_id]]
            if endpoint == "staff":
                filters = ["and", filters, ["ismain", "=", 1]]
            data = self.query(
                endpoint,
                filters=filters,
                fields=fields,
                page=page,
            )
            items.extend(data["results"])
            if not data.get("more"):
                return items
            page += 1

    def fetch_import_batch(
        self,
        vndb_id: str,
        *,
        include_related: bool = True,
    ) -> VNDBImportBatch:
        work = self.fetch_vn(vndb_id)
        if not include_related:
            return VNDBImportBatch(work=work)
        return VNDBImportBatch(
            work=work,
            releases=tuple(
                self.fetch_related(
                    "release",
                    vndb_id=vndb_id,
                    fields=self.RELEASE_FIELDS,
                )
            ),
            characters=tuple(
                self.fetch_related(
                    "character",
                    vndb_id=vndb_id,
                    fields=self.CHARACTER_FIELDS,
                )
            ),
            contributors=tuple(
                self.fetch_related(
                    "staff",
                    vndb_id=vndb_id,
                    fields=self.STAFF_FIELDS,
                )
            ),
            related_fetched=True,
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


vndb_client = VNDBClient()
