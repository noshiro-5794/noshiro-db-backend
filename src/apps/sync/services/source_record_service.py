import hashlib
import json
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.index.models import (
    CatalogSource,
    SourceNamespace,
    SourceRecord,
    SourceRecordRevision,
)
from apps.sync.exceptions import SourceCatalogConflict
from apps.sync.providers.contracts import FetchedSourceRecord, SourceNamespaceSpec


@dataclass(frozen=True, slots=True)
class RecordedSource:
    record: SourceRecord
    revision: SourceRecordRevision
    changed: bool


class SourceRecordService:
    def ensure_record(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_id: str,
        origin: str,
        canonical_url: str = "",
    ) -> SourceRecord:
        return self.ensure_records(
            namespace_spec=namespace_spec,
            external_ids=[external_id],
            origin=origin,
            canonical_urls={external_id: canonical_url},
        )[external_id]

    def record(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        fetched: FetchedSourceRecord,
        origin: str = SourceRecord.Origin.API,
    ) -> RecordedSource:
        return self.record_many(
            namespace_spec=namespace_spec,
            fetched_records=[fetched],
            origin=origin,
        )[fetched.external_id]

    @transaction.atomic
    def ensure_records(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: list[str],
        origin: str,
        canonical_urls: dict[str, str] | None = None,
    ) -> dict[str, SourceRecord]:
        cleaned_ids = {external_id.strip() for external_id in external_ids}
        if "" in cleaned_ids:
            raise ValueError("Source external_id must not be empty.")
        if not cleaned_ids:
            return {}

        namespace = self.get_or_create_namespace(namespace_spec)
        now = timezone.now()
        SourceRecord.objects.bulk_create(
            [
                SourceRecord(
                    namespace=namespace,
                    external_id=external_id,
                    canonical_url=(canonical_urls or {}).get(external_id, ""),
                    status=SourceRecord.Status.ACTIVE,
                    origin=origin,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                for external_id in cleaned_ids
            ],
            ignore_conflicts=True,
        )
        records = {
            record.external_id: record
            for record in SourceRecord.objects.filter(
                namespace=namespace,
                external_id__in=cleaned_ids,
            )
        }
        if set(records) != cleaned_ids:
            raise SourceCatalogConflict("Not all source records could be persisted.")
        records_to_update = []
        for external_id, record in records.items():
            canonical_url = (canonical_urls or {}).get(external_id)
            if canonical_url:
                record.canonical_url = canonical_url
            record.status = SourceRecord.Status.ACTIVE
            record.origin = origin
            record.last_seen_at = now
            record.updated_at = now
            records_to_update.append(record)
        SourceRecord.objects.bulk_update(
            records_to_update,
            fields=[
                "canonical_url",
                "status",
                "origin",
                "last_seen_at",
                "updated_at",
            ],
        )
        return records

    @transaction.atomic
    def record_many(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        fetched_records: list[FetchedSourceRecord],
        origin: str = SourceRecord.Origin.API,
    ) -> dict[str, RecordedSource]:
        if not fetched_records:
            return {}

        fetched_by_id = self._validate_fetched_records(fetched_records)
        namespace = self.get_or_create_namespace(namespace_spec)
        now = timezone.now()
        payload_hashes = {
            external_id: self._payload_hash(fetched.payload)
            for external_id, fetched in fetched_by_id.items()
        }

        SourceRecord.objects.bulk_create(
            [
                SourceRecord(
                    namespace=namespace,
                    external_id=external_id,
                    canonical_url=fetched.canonical_url,
                    status=SourceRecord.Status.ACTIVE,
                    origin=origin,
                    first_seen_at=fetched.fetched_at or now,
                    last_seen_at=fetched.fetched_at or now,
                )
                for external_id, fetched in fetched_by_id.items()
            ],
            ignore_conflicts=True,
        )
        records = {
            record.external_id: record
            for record in SourceRecord.objects.select_for_update().filter(
                namespace=namespace,
                external_id__in=fetched_by_id,
            )
        }
        if set(records) != set(fetched_by_id):
            raise SourceCatalogConflict("Not all source records could be persisted.")

        changed_by_id = {
            external_id: record.latest_payload_hash != payload_hashes[external_id]
            for external_id, record in records.items()
        }
        revisions_to_create = []
        for external_id, fetched in fetched_by_id.items():
            if not changed_by_id[external_id]:
                continue
            revisions_to_create.append(
                SourceRecordRevision(
                    record=records[external_id],
                    payload=fetched.payload,
                    payload_hash=payload_hashes[external_id],
                    schema_version=fetched.schema_version,
                    response_metadata=fetched.response_metadata,
                    upstream_updated_at=fetched.upstream_updated_at,
                    fetched_at=fetched.fetched_at or now,
                )
            )
        if revisions_to_create:
            SourceRecordRevision.objects.bulk_create(
                revisions_to_create,
                ignore_conflicts=True,
            )

        revision_rows = SourceRecordRevision.objects.filter(
            record_id__in=[record.pk for record in records.values()],
            payload_hash__in=payload_hashes.values(),
        )
        revisions_by_key = {
            (revision.record_id, revision.payload_hash): revision
            for revision in revision_rows
        }

        records_to_update = []
        results = {}
        for external_id, record in records.items():
            fetched = fetched_by_id[external_id]
            payload_hash = payload_hashes[external_id]
            revision = revisions_by_key.get((record.pk, payload_hash))
            if revision is None:
                raise SourceCatalogConflict(
                    f"Revision missing for {namespace}:{external_id}."
                )

            record.canonical_url = fetched.canonical_url or record.canonical_url
            record.status = SourceRecord.Status.ACTIVE
            record.origin = origin
            record.last_seen_at = fetched.fetched_at or now
            record.latest_payload_hash = payload_hash
            record.latest_revision = revision
            record.updated_at = now
            records_to_update.append(record)
            results[external_id] = RecordedSource(
                record=record,
                revision=revision,
                changed=changed_by_id[external_id],
            )

        SourceRecord.objects.bulk_update(
            records_to_update,
            fields=[
                "canonical_url",
                "status",
                "origin",
                "last_seen_at",
                "latest_payload_hash",
                "latest_revision",
                "updated_at",
            ],
        )
        return results

    @staticmethod
    def _validate_fetched_records(
        fetched_records: list[FetchedSourceRecord],
    ) -> dict[str, FetchedSourceRecord]:
        fetched_by_id = {}
        for fetched in fetched_records:
            external_id = fetched.external_id.strip()
            if not external_id:
                raise ValueError("Source external_id must not be empty.")
            if external_id in fetched_by_id:
                raise ValueError(f"Duplicate source external_id: {external_id}")
            fetched_by_id[external_id] = fetched
        return fetched_by_id

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(serialized).hexdigest()

    @staticmethod
    def get_or_create_namespace(spec: SourceNamespaceSpec) -> SourceNamespace:
        source, _ = CatalogSource.objects.get_or_create(
            slug=spec.source.slug,
            defaults={
                "name": spec.source.name,
                "base_url": spec.source.base_url,
                "terms_url": spec.source.terms_url,
                "attribution_url": spec.source.attribution_url,
                "license_name": spec.source.license_name,
            },
        )
        if not source.is_enabled:
            raise SourceCatalogConflict(f"Provider {source.slug} is disabled.")
        if source.storage_policy == CatalogSource.UsagePolicy.FORBIDDEN:
            raise SourceCatalogConflict(
                f"Provider {source.slug} forbids source payload storage."
            )
        namespace, created = SourceNamespace.objects.get_or_create(
            provider=source,
            slug=spec.slug,
            defaults={
                "resource_type": spec.resource_type,
                "description": spec.description,
            },
        )
        if not created and namespace.resource_type != spec.resource_type:
            raise SourceCatalogConflict(
                f"Namespace {namespace} is {namespace.resource_type}, "
                f"not {spec.resource_type}."
            )
        return namespace


source_record_service = SourceRecordService()
