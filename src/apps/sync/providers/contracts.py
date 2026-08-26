from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class CatalogSourceSpec:
    slug: str
    name: str
    base_url: str
    terms_url: str = ""
    attribution_url: str = ""
    license_name: str = ""


@dataclass(frozen=True, slots=True)
class SourceNamespaceSpec:
    source: CatalogSourceSpec
    slug: str
    resource_type: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class FetchedSourceRecord:
    external_id: str
    payload: dict[str, Any]
    canonical_url: str = ""
    schema_version: str = ""
    mapper_version: str = ""
    response_metadata: dict[str, Any] = field(default_factory=dict)
    upstream_updated_at: datetime | None = None
    fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CatalogPage:
    """A bounded page from a provider-wide catalog discovery endpoint."""

    external_ids: tuple[str, ...]
    next_cursor: str | None
    total_count: int | None = None


@dataclass(frozen=True, slots=True)
class DeltaPage:
    """Changed external IDs after a provider watermark."""

    external_ids: tuple[str, ...]
    next_cursor: str | None
    watermark: str
    upstream_updated_at: datetime | None = None


class ProviderCatalogContract:
    """Explicit discovery contract shared by full and incremental campaigns."""

    supports_delta = False

    def discover_full(self, *, cursor: str | None, page_size: int) -> CatalogPage:
        raise NotImplementedError

    def discover_delta(
        self, *, watermark: str, cursor: str | None, page_size: int
    ) -> DeltaPage:
        raise NotImplementedError("Provider has no reliable delta feed.")
