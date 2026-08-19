from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.contracts import (
    CatalogSourceSpec,
    FetchedSourceRecord,
    SourceNamespaceSpec,
)
from apps.sync.services.source_record_service import source_record_service

SOURCE = CatalogSourceSpec(
    slug="projection-test",
    name="Projection Test",
    base_url="https://provider.example.test",
)
NAMESPACE = SourceNamespaceSpec(
    source=SOURCE,
    slug="work-relations",
    resource_type="collection",
)
ALTERNATE_SOURCE = CatalogSourceSpec(
    slug="projection-alternate",
    name="Projection Alternate",
    base_url="https://alternate.example.test",
)
ALTERNATE_NAMESPACE = SourceNamespaceSpec(
    source=ALTERNATE_SOURCE,
    slug="work-relations",
    resource_type="collection",
)


def observation(payload: dict, *, namespace_spec=NAMESPACE):
    recorded = source_record_service.record(
        namespace_spec=namespace_spec,
        fetched=FetchedSourceRecord(
            external_id="work-1",
            payload=payload,
            mapper_version="projection-test-v1",
        ),
    )
    return knowledge_ingestion_service.record_observation(
        provider_record=recorded.record,
        mapper="projection.test",
        mapper_version="projection-test-v1",
        normalized_data=payload,
        schema_name="index.work.related",
        schema_version="1",
    )
