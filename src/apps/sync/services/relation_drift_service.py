"""Read-only relation drift detection for single-provider relation data.

Provider relation collections are imported append-only: when a provider stops
listing a relation the old ``EntityRelationEvidence`` rows remain, pointing at
an older observation. This service compares the latest relation observation of
each fetched record with what is still stored and reports relations the
provider no longer claims — without deleting or mutating anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.index.models import (
    Entity,
    EntityRelationEvidence,
    Observation,
    ProviderRecord,
    ProviderRepresentation,
)
from apps.sync.providers.bangumi import (
    BANGUMI_SUBJECT_NAMESPACE,
)
from apps.sync.services.relation_types import canonical_relation_type


@dataclass(frozen=True)
class RelationDrift:
    external_id: str
    target_external_id: str
    relation_type: str
    raw_relation: str
    last_seen_at: str


class RelationDriftService:
    RELATION_MAPPER = "bangumi.subject-relations"
    RELATION_SCHEMA = "index.work.relations"

    def audit_record(self, *, record: ProviderRecord) -> list[RelationDrift]:
        """Report relations stored for one record but absent from its latest view."""
        latest = (
            Observation.objects.filter(
                provider_record=record,
                schema_name=self.RELATION_SCHEMA,
            )
            .order_by("-observed_at", "-created_at")
            .first()
        )
        if latest is None:
            return []
        expected = self._expected_relations(latest)
        stored = self._stored_relations(record)
        newest: dict[tuple[str, str], tuple[str, str]] = {}
        for to_entity_id, relation_type, raw, observed_at in stored:
            canonical = (
                canonical_relation_type("bangumi", raw) if raw else relation_type
            )
            key = (str(to_entity_id), canonical)
            newest[key] = (raw or "", str(observed_at))
        drift: list[RelationDrift] = []
        for (to_entity_id, canonical), (raw, observed_at) in newest.items():
            if (to_entity_id, canonical) in expected:
                continue
            target = (
                ProviderRepresentation.objects.filter(
                    entity_id=to_entity_id,
                    provider_record__namespace__provider__slug="bangumi",
                    provider_record__namespace__slug=BANGUMI_SUBJECT_NAMESPACE.slug,
                    is_active=True,
                )
                .values_list("provider_record__external_id", flat=True)
                .first()
            )
            drift.append(
                RelationDrift(
                    external_id=record.external_id,
                    target_external_id=target or "",
                    relation_type=canonical,
                    raw_relation=raw,
                    last_seen_at=observed_at,
                )
            )
        return drift

    def _expected_relations(self, observation: Observation) -> set[tuple[str, str]]:
        items = (observation.normalized_data or {}).get("items") or []
        expected: set[tuple[str, str]] = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                continue
            target = self._resolve_bangumi_target(str(item["id"]))
            if target is None:
                continue
            relation_type = canonical_relation_type(
                "bangumi",
                str(item.get("relation") or "").strip().lower(),
            )
            expected.add((str(target.pk), relation_type))
        return expected

    def _stored_relations(
        self, record: ProviderRecord
    ) -> list[tuple[str, str, str, Any]]:
        source = (
            ProviderRepresentation.objects.filter(
                provider_record__namespace__provider__slug="bangumi",
                provider_record__namespace__slug=BANGUMI_SUBJECT_NAMESPACE.slug,
                provider_record__external_id=record.external_id,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        if source is None:
            return []
        rows = (
            EntityRelationEvidence.objects.filter(
                relation__from_entity=source.entity,
                observation__provider_record=record,
            )
            .select_related("relation", "observation")
            .order_by("observation__observed_at", "id")
            .values_list(
                "relation__to_entity_id",
                "relation__relation_type",
                "raw_relation",
                "observation__observed_at",
            )
        )
        return list(rows)

    @staticmethod
    def _resolve_bangumi_target(external_id: str) -> Entity | None:
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record__namespace__provider__slug="bangumi",
                provider_record__namespace__slug=BANGUMI_SUBJECT_NAMESPACE.slug,
                provider_record__external_id=external_id,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        return representation.entity if representation is not None else None


relation_drift_service = RelationDriftService()
