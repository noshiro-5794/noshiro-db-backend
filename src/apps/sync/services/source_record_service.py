import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import models, transaction
from django.utils import timezone

from apps.index.models import (
    CatalogSource,
    Character,
    CharacterExternalIdentity,
    Episode,
    EpisodeExternalIdentity,
    SourceNamespace,
    SourceRecord,
    SourceRecordRevision,
    Staff,
    StaffExternalIdentity,
    Subject,
    SubjectExternalIdentity,
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
    def ensure_legacy_records(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: list[str],
    ) -> dict[str, SourceRecord]:
        return self.ensure_records(
            namespace_spec=namespace_spec,
            external_ids=external_ids,
            origin=SourceRecord.Origin.LEGACY_PROJECTION,
        )

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
        if origin != SourceRecord.Origin.LEGACY_PROJECTION:
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


class SourceIdentityService:
    def resolve_subject(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_id: str,
        legacy_source: str,
    ) -> Subject | None:
        return self.resolve_subjects(
            namespace_spec=namespace_spec,
            external_ids={external_id},
            legacy_source=legacy_source,
        ).get(external_id.strip())

    def resolve_subjects(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
        legacy_source: str,
    ) -> dict[str, Subject]:
        return self._resolve_targets(
            identity_model=SubjectExternalIdentity,
            target_model=Subject,
            target_field="subject",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
            legacy_source=legacy_source,
        )

    def resolve_episodes(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
        legacy_source: str,
    ) -> dict[str, Episode]:
        return self._resolve_targets(
            identity_model=EpisodeExternalIdentity,
            target_model=Episode,
            target_field="episode",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
            legacy_source=legacy_source,
        )

    def resolve_staff_members(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
        legacy_source: str,
    ) -> dict[str, Staff]:
        return self._resolve_targets(
            identity_model=StaffExternalIdentity,
            target_model=Staff,
            target_field="staff",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
            legacy_source=legacy_source,
        )

    def resolve_characters(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
        legacy_source: str,
    ) -> dict[str, Character]:
        return self._resolve_targets(
            identity_model=CharacterExternalIdentity,
            target_model=Character,
            target_field="character",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
            legacy_source=legacy_source,
        )

    def find_subject(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_id: str,
    ) -> Subject | None:
        return self._find_target(
            identity_model=SubjectExternalIdentity,
            target_field="subject",
            namespace_spec=namespace_spec,
            external_id=external_id,
        )

    def find_subjects(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
    ) -> dict[str, Subject]:
        return self._find_targets(
            identity_model=SubjectExternalIdentity,
            target_field="subject",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
        )

    def find_episodes(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
    ) -> dict[str, Episode]:
        return self._find_targets(
            identity_model=EpisodeExternalIdentity,
            target_field="episode",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
        )

    def find_staff_members(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
    ) -> dict[str, Staff]:
        return self._find_targets(
            identity_model=StaffExternalIdentity,
            target_field="staff",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
        )

    def find_characters(
        self,
        *,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
    ) -> dict[str, Character]:
        return self._find_targets(
            identity_model=CharacterExternalIdentity,
            target_field="character",
            namespace_spec=namespace_spec,
            external_ids=external_ids,
        )

    def get_subject_external_id(
        self,
        *,
        subject: Subject,
        namespace_spec: SourceNamespaceSpec,
    ) -> str | None:
        return self._get_external_id(
            identity_model=SubjectExternalIdentity,
            target_field="subject",
            target=subject,
            namespace_spec=namespace_spec,
        )

    def resolve_subject_external_id(
        self,
        *,
        subject: Subject,
        namespace_spec: SourceNamespaceSpec,
        legacy_source: str,
    ) -> str | None:
        external_id = self.get_subject_external_id(
            subject=subject,
            namespace_spec=namespace_spec,
        )
        if external_id is not None:
            return external_id
        if self._target_has_namespace_identity(
            identity_model=SubjectExternalIdentity,
            target_field="subject",
            target=subject,
            namespace_spec=namespace_spec,
        ):
            return None
        return subject.id_source if subject.info_source == legacy_source else None

    @staticmethod
    def _find_target(
        *,
        identity_model: type[models.Model],
        target_field: str,
        namespace_spec: SourceNamespaceSpec,
        external_id: str,
    ) -> models.Model | None:
        cleaned_id = external_id.strip()
        if not cleaned_id:
            return None

        identity = (
            identity_model.objects.select_related(target_field)
            .filter(
                source_record__namespace__provider__slug=namespace_spec.source.slug,
                source_record__namespace__slug=namespace_spec.slug,
                source_record__external_id=cleaned_id,
                source_record__status=SourceRecord.Status.ACTIVE,
            )
            .first()
        )
        return getattr(identity, target_field) if identity is not None else None

    @staticmethod
    def _find_targets(
        *,
        identity_model: type[models.Model],
        target_field: str,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
    ) -> dict[str, models.Model]:
        cleaned_ids = {external_id.strip() for external_id in external_ids}
        cleaned_ids.discard("")
        if not cleaned_ids:
            return {}

        identities = identity_model.objects.select_related(
            target_field,
            "source_record",
        ).filter(
            source_record__namespace__provider__slug=namespace_spec.source.slug,
            source_record__namespace__slug=namespace_spec.slug,
            source_record__external_id__in=cleaned_ids,
            source_record__status=SourceRecord.Status.ACTIVE,
        )
        return {
            identity.source_record.external_id: getattr(identity, target_field)
            for identity in identities
        }

    @staticmethod
    def _get_external_id(
        *,
        identity_model: type[models.Model],
        target_field: str,
        target: models.Model,
        namespace_spec: SourceNamespaceSpec,
    ) -> str | None:
        return (
            identity_model.objects.filter(
                **{
                    target_field: target,
                    "source_record__namespace__provider__slug": (
                        namespace_spec.source.slug
                    ),
                    "source_record__namespace__slug": namespace_spec.slug,
                    "source_record__status": SourceRecord.Status.ACTIVE,
                }
            )
            .values_list("source_record__external_id", flat=True)
            .first()
        )

    @classmethod
    def _resolve_targets(
        cls,
        *,
        identity_model: type[models.Model],
        target_model: type[models.Model],
        target_field: str,
        namespace_spec: SourceNamespaceSpec,
        external_ids: set[str],
        legacy_source: str,
    ) -> dict[str, models.Model]:
        cleaned_ids = {external_id.strip() for external_id in external_ids}
        cleaned_ids.discard("")
        if not cleaned_ids:
            return {}

        resolved = cls._find_targets(
            identity_model=identity_model,
            target_field=target_field,
            namespace_spec=namespace_spec,
            external_ids=cleaned_ids,
        )
        legacy_targets = list(
            target_model.objects.filter(
                info_source=legacy_source,
                id_source__in=cleaned_ids,
            )
        )
        if not legacy_targets:
            return resolved

        target_ids = [target.pk for target in legacy_targets]
        namespace_identities = identity_model.objects.select_related(
            "source_record"
        ).filter(
            **{
                f"{target_field}_id__in": target_ids,
                "source_record__namespace__provider__slug": (
                    namespace_spec.source.slug
                ),
                "source_record__namespace__slug": namespace_spec.slug,
            }
        )
        external_ids_by_target: dict[object, set[str]] = {}
        for identity in namespace_identities:
            target_id = getattr(identity, f"{target_field}_id")
            external_ids_by_target.setdefault(target_id, set()).add(
                identity.source_record.external_id
            )

        for target in legacy_targets:
            external_id = target.id_source
            resolved_target = resolved.get(external_id)
            if resolved_target is not None and resolved_target.pk != target.pk:
                raise SourceCatalogConflict(
                    f"Legacy {legacy_source}:{external_id} conflicts with its "
                    "catalog identity."
                )

            bound_external_ids = external_ids_by_target.get(target.pk, set())
            if bound_external_ids:
                if external_id not in bound_external_ids:
                    raise SourceCatalogConflict(
                        f"Legacy {legacy_source}:{external_id} conflicts with "
                        f"namespace identities {sorted(bound_external_ids)}."
                    )
                # An inactive identity must not be revived through legacy fields.
                continue
            resolved[external_id] = target
        return resolved

    @staticmethod
    def _target_has_namespace_identity(
        *,
        identity_model: type[models.Model],
        target_field: str,
        target: models.Model,
        namespace_spec: SourceNamespaceSpec,
    ) -> bool:
        return identity_model.objects.filter(
            **{
                target_field: target,
                "source_record__namespace__provider__slug": namespace_spec.source.slug,
                "source_record__namespace__slug": namespace_spec.slug,
            }
        ).exists()

    def bind_subject(
        self,
        *,
        subject: Subject,
        source_record: SourceRecord,
        match_method: str,
        confidence: Decimal = Decimal("1"),
        make_primary: bool = True,
    ) -> SubjectExternalIdentity:
        return self._bind(
            identity_model=SubjectExternalIdentity,
            target_field="subject",
            target=subject,
            source_record=source_record,
            expected_resource_type=SourceNamespace.ResourceType.SUBJECT,
            match_method=match_method,
            confidence=confidence,
            make_primary=make_primary,
        )

    def bind_episode(
        self,
        *,
        episode: Episode,
        source_record: SourceRecord,
        match_method: str,
        confidence: Decimal = Decimal("1"),
        make_primary: bool = True,
    ) -> EpisodeExternalIdentity:
        return self._bind(
            identity_model=EpisodeExternalIdentity,
            target_field="episode",
            target=episode,
            source_record=source_record,
            expected_resource_type=SourceNamespace.ResourceType.EPISODE,
            match_method=match_method,
            confidence=confidence,
            make_primary=make_primary,
        )

    def bind_staff(
        self,
        *,
        staff: Staff,
        source_record: SourceRecord,
        match_method: str,
        confidence: Decimal = Decimal("1"),
        make_primary: bool = True,
    ) -> StaffExternalIdentity:
        return self._bind(
            identity_model=StaffExternalIdentity,
            target_field="staff",
            target=staff,
            source_record=source_record,
            expected_resource_type=SourceNamespace.ResourceType.PERSON,
            match_method=match_method,
            confidence=confidence,
            make_primary=make_primary,
        )

    def bind_character(
        self,
        *,
        character: Character,
        source_record: SourceRecord,
        match_method: str,
        confidence: Decimal = Decimal("1"),
        make_primary: bool = True,
    ) -> CharacterExternalIdentity:
        return self._bind(
            identity_model=CharacterExternalIdentity,
            target_field="character",
            target=character,
            source_record=source_record,
            expected_resource_type=SourceNamespace.ResourceType.CHARACTER,
            match_method=match_method,
            confidence=confidence,
            make_primary=make_primary,
        )

    def bind_subjects(
        self,
        *,
        bindings: list[tuple[Subject, SourceRecord]],
        match_method: str,
        make_primary: bool = True,
    ) -> int:
        return self._bind_many(
            identity_model=SubjectExternalIdentity,
            target_field="subject",
            bindings=bindings,
            expected_resource_type=SourceNamespace.ResourceType.SUBJECT,
            match_method=match_method,
            make_primary=make_primary,
        )

    def bind_episodes(
        self,
        *,
        bindings: list[tuple[Episode, SourceRecord]],
        match_method: str,
        make_primary: bool = True,
    ) -> int:
        return self._bind_many(
            identity_model=EpisodeExternalIdentity,
            target_field="episode",
            bindings=bindings,
            expected_resource_type=SourceNamespace.ResourceType.EPISODE,
            match_method=match_method,
            make_primary=make_primary,
        )

    def bind_staff_members(
        self,
        *,
        bindings: list[tuple[Staff, SourceRecord]],
        match_method: str,
        make_primary: bool = True,
    ) -> int:
        return self._bind_many(
            identity_model=StaffExternalIdentity,
            target_field="staff",
            bindings=bindings,
            expected_resource_type=SourceNamespace.ResourceType.PERSON,
            match_method=match_method,
            make_primary=make_primary,
        )

    def bind_characters(
        self,
        *,
        bindings: list[tuple[Character, SourceRecord]],
        match_method: str,
        make_primary: bool = True,
    ) -> int:
        return self._bind_many(
            identity_model=CharacterExternalIdentity,
            target_field="character",
            bindings=bindings,
            expected_resource_type=SourceNamespace.ResourceType.CHARACTER,
            match_method=match_method,
            make_primary=make_primary,
        )

    @staticmethod
    @transaction.atomic
    def _bind(
        *,
        identity_model: type[models.Model],
        target_field: str,
        target: models.Model,
        source_record: SourceRecord,
        expected_resource_type: str,
        match_method: str,
        confidence: Decimal,
        make_primary: bool,
    ) -> models.Model:
        if source_record.namespace.resource_type != expected_resource_type:
            raise SourceCatalogConflict(
                f"Cannot bind {source_record.namespace.resource_type} record "
                f"as {expected_resource_type}."
            )

        existing = (
            identity_model.objects.select_for_update()
            .filter(source_record=source_record)
            .first()
        )
        target_id = target.pk
        if existing is not None:
            if getattr(existing, f"{target_field}_id") != target_id:
                raise SourceCatalogConflict(
                    f"{source_record} is already bound to another {target_field}."
                )
            return existing

        has_primary = identity_model.objects.filter(
            **{target_field: target, "is_primary": True}
        ).exists()
        return identity_model.objects.create(
            **{
                target_field: target,
                "source_record": source_record,
                "match_method": match_method,
                "confidence": confidence,
                "is_primary": make_primary and not has_primary,
            }
        )

    @staticmethod
    @transaction.atomic
    def _bind_many(
        *,
        identity_model: type[models.Model],
        target_field: str,
        bindings: list[tuple[models.Model, SourceRecord]],
        expected_resource_type: str,
        match_method: str,
        make_primary: bool,
    ) -> int:
        if not bindings:
            return 0

        records_by_id = {}
        targets_by_record_id = {}
        for target, record in bindings:
            if record.pk in records_by_id:
                raise SourceCatalogConflict(
                    f"Duplicate identity binding for source record {record.pk}."
                )
            records_by_id[record.pk] = record
            targets_by_record_id[record.pk] = target

        resource_types = set(
            SourceRecord.objects.filter(pk__in=records_by_id)
            .values_list("namespace__resource_type", flat=True)
            .distinct()
        )
        if resource_types != {expected_resource_type}:
            raise SourceCatalogConflict(
                f"Expected {expected_resource_type} records, got {resource_types}."
            )

        existing_by_record_id = {
            identity.source_record_id: identity
            for identity in identity_model.objects.select_for_update().filter(
                source_record_id__in=records_by_id
            )
        }
        for record_id, identity in existing_by_record_id.items():
            expected_target_id = targets_by_record_id[record_id].pk
            if getattr(identity, f"{target_field}_id") != expected_target_id:
                raise SourceCatalogConflict(
                    f"Source record {record_id} is bound to another {target_field}."
                )

        target_ids = [target.pk for target, _record in bindings]
        primary_target_ids = set(
            identity_model.objects.filter(
                **{f"{target_field}_id__in": target_ids, "is_primary": True}
            ).values_list(f"{target_field}_id", flat=True)
        )
        identities_to_create = []
        for target, record in bindings:
            if record.pk in existing_by_record_id:
                continue
            is_primary = make_primary and target.pk not in primary_target_ids
            identities_to_create.append(
                identity_model(
                    **{
                        target_field: target,
                        "source_record": record,
                        "match_method": match_method,
                        "confidence": Decimal("1"),
                        "is_primary": is_primary,
                    }
                )
            )
            if is_primary:
                primary_target_ids.add(target.pk)

        identity_model.objects.bulk_create(
            identities_to_create,
            ignore_conflicts=True,
        )
        return len(identities_to_create)


source_record_service = SourceRecordService()
source_identity_service = SourceIdentityService()
