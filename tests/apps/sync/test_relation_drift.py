import hashlib
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.index.models import (
    Entity,
    EntityRelation,
    EntityRelationEvidence,
    Observation,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
)
from apps.sync.providers.bangumi import (
    BANGUMI_SUBJECT_NAMESPACE,
    BANGUMI_SUBJECT_RELATIONS_NAMESPACE,
)
from apps.sync.services.relation_drift_service import relation_drift_service

pytestmark = pytest.mark.django_db(transaction=True)


def _hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _entity(
    *,
    provider: Provider,
    namespace_slug: str,
    external_id: str,
) -> tuple[ProviderRecord, Entity]:
    namespace, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug=namespace_slug,
        defaults={"resource_type": ProviderNamespace.ResourceType.SUBJECT},
    )
    record = ProviderRecord.objects.create(
        namespace=namespace,
        external_id=external_id,
        origin="api",
        status="active",
    )
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    ProviderRepresentation.objects.create(
        provider_record=record,
        entity=entity,
        mapping_kind=ProviderRepresentation.MappingKind.EXACT,
        method=ProviderRepresentation.Method.EXTERNAL_ID,
    )
    return record, entity


def _observation(
    *, relation_record: ProviderRecord, items: list[dict], minutes_ago: int
) -> Observation:
    return Observation.objects.create(
        provider_record=relation_record,
        origin=Observation.Origin.LEGACY,
        schema_name="index.work.relations",
        schema_version="1",
        normalized_data={"items": items},
        normalized_hash=_hash({"items": items}),
        observed_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


def test_audit_reports_provider_removed_relations() -> None:
    provider = Provider.objects.create(slug="bangumi", name="Bangumi")
    _, source_entity = _entity(
        provider=provider,
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        external_id="100",
    )
    _, target_kept = _entity(
        provider=provider,
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        external_id="200",
    )
    _, target_removed = _entity(
        provider=provider,
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        external_id="300",
    )
    relation_record = ProviderRecord.objects.create(
        namespace=ProviderNamespace.objects.create(
            provider=provider,
            slug=BANGUMI_SUBJECT_RELATIONS_NAMESPACE.slug,
            resource_type=ProviderNamespace.ResourceType.COLLECTION,
        ),
        external_id="100",
        origin="api",
        status="active",
    )
    old = _observation(
        relation_record=relation_record,
        items=[
            {"id": 200, "relation": "续作"},
            {"id": 300, "relation": "前传"},
        ],
        minutes_ago=60,
    )
    latest = _observation(
        relation_record=relation_record,
        items=[{"id": 200, "relation": "续作"}],
        minutes_ago=1,
    )
    for from_entity, to_entity, raw in (
        (source_entity, target_kept, "续作"),
        (source_entity, target_removed, "前传"),
    ):
        relation, _ = EntityRelation.objects.get_or_create(
            from_entity=from_entity,
            to_entity=to_entity,
            relation_type="sequel" if raw == "续作" else "prequel",
        )
        EntityRelationEvidence.objects.create(
            relation=relation,
            observation=old,
            json_pointer="/items/0",
            raw_relation=raw,
        )
    _ = latest

    drift = relation_drift_service.audit_record(record=relation_record)

    assert len(drift) == 1
    assert drift[0].target_external_id == "300"
    assert drift[0].relation_type == "prequel"
    assert drift[0].external_id == "100"


def test_audit_is_clean_when_latest_view_matches_stored() -> None:
    provider = Provider.objects.create(slug="bangumi", name="Bangumi")
    _, source_entity = _entity(
        provider=provider,
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        external_id="100",
    )
    _, target = _entity(
        provider=provider,
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        external_id="200",
    )
    relation_record = ProviderRecord.objects.create(
        namespace=ProviderNamespace.objects.create(
            provider=provider,
            slug=BANGUMI_SUBJECT_RELATIONS_NAMESPACE.slug,
            resource_type=ProviderNamespace.ResourceType.COLLECTION,
        ),
        external_id="100",
        origin="api",
        status="active",
    )
    observation = _observation(
        relation_record=relation_record,
        items=[{"id": 200, "relation": "续作"}],
        minutes_ago=5,
    )
    relation, _ = EntityRelation.objects.get_or_create(
        from_entity=source_entity,
        to_entity=target,
        relation_type="sequel",
    )
    EntityRelationEvidence.objects.create(
        relation=relation,
        observation=observation,
        json_pointer="/items/0",
        raw_relation="续作",
    )

    drift = relation_drift_service.audit_record(record=relation_record)

    assert drift == []


def test_legacy_generic_type_is_not_reported_when_raw_matches_latest() -> None:
    provider = Provider.objects.create(slug="bangumi", name="Bangumi")
    _, source_entity = _entity(
        provider=provider,
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        external_id="100",
    )
    _, target = _entity(
        provider=provider,
        namespace_slug=BANGUMI_SUBJECT_NAMESPACE.slug,
        external_id="200",
    )
    relation_record = ProviderRecord.objects.create(
        namespace=ProviderNamespace.objects.create(
            provider=provider,
            slug=BANGUMI_SUBJECT_RELATIONS_NAMESPACE.slug,
            resource_type=ProviderNamespace.ResourceType.COLLECTION,
        ),
        external_id="100",
        origin="api",
        status="active",
    )
    latest = _observation(
        relation_record=relation_record,
        items=[{"id": 200, "relation": "衍生"}],
        minutes_ago=1,
    )
    legacy, _ = EntityRelation.objects.get_or_create(
        from_entity=source_entity,
        to_entity=target,
        relation_type="related",
    )
    EntityRelationEvidence.objects.create(
        relation=legacy,
        observation=latest,
        json_pointer="/items/0",
        raw_relation="衍生",
    )

    drift = relation_drift_service.audit_record(record=relation_record)

    assert drift == []
