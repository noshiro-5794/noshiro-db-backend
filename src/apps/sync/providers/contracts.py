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
