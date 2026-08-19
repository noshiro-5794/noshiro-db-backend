from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.text import slugify

from apps.index.models import (
    Appearance,
    ContentRating,
    Contributor,
    Credit,
    Entity,
    EntityDescription,
    EntityMedia,
    EntityName,
    EntityRelation,
    EntityRelationEvidence,
    EntityTerm,
    ExternalLink,
    GalgameProfile,
    IndexCollection,
    IndexMembership,
    MediaAsset,
    MetricSnapshot,
    Organization,
    Person,
    Predicate,
    ProviderRecord,
    ProviderRepresentation,
    Release,
    ReleaseWork,
    ReleaseWorkEvidence,
    Taxonomy,
    Term,
    TermLabel,
    TermMapping,
    VoicePerformance,
    Work,
)
from apps.index.selectors.current import current_appearances
from apps.index.services import (
    cross_provider_identity_service,
    entity_resolution_service,
    knowledge_ingestion_service,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.providers.vndb import (
    VNDB_CHARACTER_NAMESPACE,
    VNDB_PRODUCER_NAMESPACE,
    VNDB_RELATED_NAMESPACE,
    VNDB_RELEASE_NAMESPACE,
    VNDB_STAFF_ALIAS_NAMESPACE,
    VNDB_STAFF_NAMESPACE,
    VNDB_TAG_NAMESPACE,
    VNDB_TRAIT_NAMESPACE,
    VNDB_VN_NAMESPACE,
    VNDBImportBatch,
    vndb_client,
)
from apps.sync.services.source_record_service import source_record_service


class VNDBImportService:
    def import_work(self, *, vndb_id: str, include_related: bool = True) -> Entity:
        if not vndb_id.startswith("v"):
            raise ValueError("VNDB work IDs must start with 'v'.")
        batch = vndb_client.fetch_import_batch(
            vndb_id,
            include_related=include_related,
        )
        return self._persist_batch(vndb_id=vndb_id, batch=batch)

    @transaction.atomic
    def _persist_batch(self, *, vndb_id: str, batch: VNDBImportBatch) -> Entity:
        data = batch.work
        recorded = source_record_service.record(
            namespace_spec=VNDB_VN_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id=vndb_id,
                payload=data,
                canonical_url=f"https://vndb.org/{vndb_id}",
                schema_version="vndb-kana",
                mapper_version="vndb-vn-v1",
            ),
        )
        observation = knowledge_ingestion_service.record_observation(
            provider_record=recorded.record,
            mapper="vndb.vn",
            mapper_version="vndb-vn-v1",
            normalized_data=data,
            schema_name="index.work",
            schema_version="1",
        )
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record=recorded.record,
                mapping_kind=ProviderRepresentation.MappingKind.EXACT,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        if representation is None:
            entity = Entity.objects.create(
                kind=Entity.Kind.WORK,
                audience=self._audience_from_vn(data),
            )
            work = Work.objects.create(entity=entity, work_type=Work.WorkType.GALGAME)
            GalgameProfile.objects.create(
                work=work,
                playtime_minutes=self._positive_int(data.get("length_minutes")),
                development_status=self._development_status(data.get("devstatus")),
            )
            ProviderRepresentation.objects.create(
                provider_record=recorded.record,
                entity=entity,
                mapping_kind=ProviderRepresentation.MappingKind.EXACT,
                method=ProviderRepresentation.Method.PROVIDER,
                confidence=1,
            )
        else:
            entity = representation.entity
            work, _ = Work.objects.update_or_create(
                entity=entity,
                defaults={"work_type": Work.WorkType.GALGAME},
            )
            GalgameProfile.objects.update_or_create(
                work=work,
                defaults={
                    "playtime_minutes": self._positive_int(data.get("length_minutes")),
                    "development_status": self._development_status(
                        data.get("devstatus")
                    ),
                },
            )
        self._upsert_names(
            entity=entity, record=recorded.record, observation=observation, data=data
        )
        self._upsert_description(
            entity=entity, record=recorded.record, observation=observation, data=data
        )
        self._upsert_image(
            entity=entity, record=recorded.record, observation=observation, data=data
        )
        self._upsert_screenshots(
            entity=entity, record=recorded.record, observation=observation, data=data
        )
        self._upsert_external_links(
            entity=entity, record=recorded.record, observation=observation, data=data
        )
        self._upsert_metrics(entity=entity, record=recorded.record, data=data)
        self._upsert_tags(entity=entity, observation=observation, data=data)
        self._upsert_work_facts(
            entity=entity,
            observation=observation,
            data=data,
        )
        self._import_developers(
            work=work,
            observation=observation,
            items=tuple(data.get("developers") or ()),
        )
        self._import_staff_credits(
            work=work,
            observation=observation,
            items=tuple(data.get("staff") or ()),
        )
        self._import_relations(
            entity=entity,
            observation=observation,
            items=tuple(data.get("relations") or ()),
        )
        collection, _ = IndexCollection.objects.get_or_create(
            slug="galgame", defaults={"name": "Galgame"}
        )
        IndexMembership.objects.update_or_create(
            collection=collection,
            entity=entity,
            defaults={
                "listing_state": IndexMembership.State.LISTED,
                "inclusion_reason": "VNDB visual novel",
            },
        )
        if batch.related_fetched:
            related_data = {
                "releases": batch.releases,
                "characters": batch.characters,
                "contributors": batch.contributors,
            }
            related_recorded = source_record_service.record(
                namespace_spec=VNDB_RELATED_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id=vndb_id,
                    payload=related_data,
                    canonical_url=f"https://vndb.org/{vndb_id}",
                    schema_version="vndb-kana",
                    mapper_version="vndb-vn-related-v1",
                ),
            )
            related_observation = knowledge_ingestion_service.record_observation(
                provider_record=related_recorded.record,
                mapper="vndb.vn.related",
                mapper_version="vndb-vn-related-v1",
                normalized_data=related_data,
                schema_name="index.work.related",
                schema_version="1",
            )
            self._import_releases(
                work=work,
                vndb_id=vndb_id,
                relationship_observation=related_observation,
                items=batch.releases,
            )
            self._import_characters(
                work=work,
                vndb_id=vndb_id,
                relationship_observation=related_observation,
                items=batch.characters,
            )
            self._import_staff(items=batch.contributors)
        self._import_voice_performances(
            work=work,
            observation=observation,
            items=tuple(data.get("va") or ()),
        )
        cross_provider_identity_service.reconcile_vndb_work(
            entity=entity,
            vndb_id=vndb_id,
        )
        return entity_resolution_service.resolve(entity)

    def _import_releases(
        self,
        *,
        work: Work,
        vndb_id: str,
        relationship_observation,
        items: tuple[dict, ...],
    ) -> None:
        for index, item in enumerate(items):
            external_id = item.get("id")
            if not isinstance(external_id, str):
                continue
            recorded = source_record_service.record(
                namespace_spec=VNDB_RELEASE_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id=external_id,
                    payload=item,
                    canonical_url=f"https://vndb.org/{external_id}",
                    schema_version="vndb-kana",
                    mapper_version="vndb-release-v1",
                ),
            )
            observation = knowledge_ingestion_service.record_observation(
                provider_record=recorded.record,
                mapper="vndb.release",
                mapper_version="vndb-release-v1",
                normalized_data=item,
                schema_name="index.release",
                schema_version="1",
            )
            representation = (
                ProviderRepresentation.objects.filter(
                    provider_record=recorded.record, is_active=True
                )
                .select_related("entity")
                .first()
            )
            entity = (
                representation.entity
                if representation
                else Entity.objects.create(
                    kind=Entity.Kind.RELEASE,
                    audience=(
                        Entity.Audience.ADULT
                        if self._positive_int(item.get("minage"), default=0) >= 18
                        else Entity.Audience.GENERAL
                    ),
                )
            )
            start, end, precision = self._partial_date(item.get("released"))
            release, _ = Release.objects.update_or_create(
                entity=entity,
                defaults={
                    "release_type": "patch" if item.get("patch") else "edition",
                    "date_start": start,
                    "date_end": end,
                    "date_precision": precision,
                    "date_raw": item.get("released") or "",
                    "platform": ",".join(item.get("platforms") or [])[:64],
                    "is_official": item.get("official"),
                    "is_patch": bool(item.get("patch")),
                },
            )
            vns = [row for row in item.get("vns") or [] if row.get("id") == vndb_id]
            for vn_index, vn in enumerate(vns):
                raw_role = vn.get("rtype") or "complete"
                release_work, _ = ReleaseWork.objects.get_or_create(
                    release=release,
                    work=work,
                    role=self._release_work_role(raw_role),
                )
                ReleaseWorkEvidence.objects.get_or_create(
                    release_work=release_work,
                    observation=relationship_observation,
                    json_pointer=f"/releases/{index}/vns/{vn_index}",
                    defaults={"raw_role": str(raw_role)[:64]},
                )
            ProviderRepresentation.objects.update_or_create(
                provider_record=recorded.record,
                entity=entity,
                mapping_kind=ProviderRepresentation.MappingKind.EXACT,
                defaults={
                    "method": ProviderRepresentation.Method.PROVIDER,
                    "confidence": 1,
                    "is_active": True,
                },
            )
            title = item.get("title") or item.get("alttitle")
            if isinstance(title, str) and title:
                EntityName.objects.get_or_create(
                    entity=entity,
                    provider_record=recorded.record,
                    observation=observation,
                    text=title,
                    language="",
                    kind=EntityName.Kind.OFFICIAL,
                    defaults={"is_official": True},
                )
            min_age = self._positive_int(item.get("minage"))
            if min_age is not None:
                ContentRating.objects.get_or_create(
                    entity=entity,
                    system="vndb-minage",
                    value=str(min_age),
                    region="",
                    provider_record=recorded.record,
                    observation=observation,
                    defaults={"minimum_age": min_age},
                )
            self._upsert_external_links(
                entity=entity,
                record=recorded.record,
                observation=observation,
                data=item,
            )
            self._upsert_release_facts(
                entity=entity,
                observation=observation,
                data=item,
            )
            self._import_release_producers(
                release_entity=entity,
                observation=observation,
                items=tuple(item.get("producers") or ()),
            )

    def _import_characters(
        self,
        *,
        work: Work,
        vndb_id: str,
        relationship_observation,
        items: tuple[dict, ...],
    ) -> None:
        for item in items:
            external_id = item.get("id")
            if not isinstance(external_id, str):
                continue
            recorded = source_record_service.record(
                namespace_spec=VNDB_CHARACTER_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id=external_id,
                    payload=item,
                    canonical_url=f"https://vndb.org/{external_id}",
                    schema_version="vndb-kana",
                    mapper_version="vndb-character-v1",
                ),
            )
            observation = knowledge_ingestion_service.record_observation(
                provider_record=recorded.record,
                mapper="vndb.character",
                mapper_version="vndb-character-v1",
                normalized_data=item,
                schema_name="index.character",
                schema_version="1",
            )
            representation = (
                ProviderRepresentation.objects.filter(
                    provider_record=recorded.record, is_active=True
                )
                .select_related("entity")
                .first()
            )
            entity = (
                representation.entity
                if representation
                else Entity.objects.create(kind=Entity.Kind.CHARACTER)
            )
            ProviderRepresentation.objects.update_or_create(
                provider_record=recorded.record,
                entity=entity,
                mapping_kind=ProviderRepresentation.MappingKind.EXACT,
                defaults={
                    "method": ProviderRepresentation.Method.PROVIDER,
                    "confidence": 1,
                    "is_active": True,
                },
            )
            self._simple_names(
                entity=entity,
                record=recorded.record,
                observation=observation,
                data=item,
            )
            self._upsert_description(
                entity=entity,
                record=recorded.record,
                observation=observation,
                data=item,
            )
            self._upsert_image(
                entity=entity,
                record=recorded.record,
                observation=observation,
                data=item,
            )
            appearances = [
                row for row in item.get("vns") or [] if row.get("id") == vndb_id
            ]
            role = next(
                (row.get("role") or "" for row in appearances),
                "",
            )
            spoiler_level = max(
                (
                    self._bounded_spoiler_level(row.get("spoiler"))
                    for row in appearances
                ),
                default=0,
            )
            if appearances:
                Appearance.objects.get_or_create(
                    work=work,
                    character_entity=entity,
                    role=role,
                    observation=relationship_observation,
                    defaults={"spoiler_level": spoiler_level},
                )
            self._upsert_traits(
                entity=entity,
                observation=observation,
                items=tuple(item.get("traits") or ()),
            )
            self._upsert_character_facts(
                entity=entity,
                observation=observation,
                data=item,
            )

    def _import_staff(
        self,
        *,
        items: tuple[dict, ...],
    ) -> None:
        for item in items:
            external_id = item.get("id")
            if not isinstance(external_id, str):
                continue
            recorded = source_record_service.record(
                namespace_spec=VNDB_STAFF_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id=external_id,
                    payload=item,
                    canonical_url=f"https://vndb.org/{external_id}",
                    schema_version="vndb-kana",
                    mapper_version="vndb-staff-v1",
                ),
            )
            observation = knowledge_ingestion_service.record_observation(
                provider_record=recorded.record,
                mapper="vndb.staff",
                mapper_version="vndb-staff-v1",
                normalized_data=item,
                schema_name="index.contributor",
                schema_version="1",
            )
            representation = (
                ProviderRepresentation.objects.filter(
                    provider_record=recorded.record, is_active=True
                )
                .select_related("entity")
                .first()
            )
            entity = (
                representation.entity
                if representation
                else Entity.objects.create(kind=Entity.Kind.CONTRIBUTOR)
            )
            contributor, _ = Contributor.objects.update_or_create(
                entity=entity,
                defaults={"kind": Contributor.Kind.PERSON},
            )
            Person.objects.get_or_create(contributor=contributor)
            ProviderRepresentation.objects.update_or_create(
                provider_record=recorded.record,
                entity=entity,
                mapping_kind=ProviderRepresentation.MappingKind.EXACT,
                defaults={
                    "method": ProviderRepresentation.Method.PROVIDER,
                    "confidence": 1,
                    "is_active": True,
                },
            )
            self._simple_names(
                entity=entity,
                record=recorded.record,
                observation=observation,
                data=item,
            )
            self._upsert_staff_aliases(
                entity=entity,
                staff_record=recorded.record,
                observation=observation,
                aliases=tuple(item.get("aliases") or ()),
            )
            self._upsert_description(
                entity=entity,
                record=recorded.record,
                observation=observation,
                data=item,
            )
            self._upsert_external_links(
                entity=entity,
                record=recorded.record,
                observation=observation,
                data=item,
            )

    def _import_developers(
        self,
        *,
        work: Work,
        observation,
        items: tuple[dict, ...],
    ) -> None:
        for item in items:
            contributor = self._upsert_producer(item, observation=observation)
            if contributor is None:
                continue
            Credit.objects.get_or_create(
                work=work,
                contributor=contributor,
                role="developer",
                credited_as=self._credited_name(item),
                observation=observation,
            )

    def _import_release_producers(
        self,
        *,
        release_entity: Entity,
        observation,
        items: tuple[dict, ...],
    ) -> None:
        for index, item in enumerate(items):
            contributor = self._upsert_producer(item, observation=observation)
            if contributor is None:
                continue
            roles = []
            if item.get("developer"):
                roles.append("release-developer")
            if item.get("publisher"):
                roles.append("release-publisher")
            for relation_type in roles:
                relation, _ = EntityRelation.objects.get_or_create(
                    from_entity=release_entity,
                    to_entity=contributor.entity,
                    relation_type=relation_type,
                )
                EntityRelationEvidence.objects.get_or_create(
                    relation=relation,
                    observation=observation,
                    json_pointer=f"/producers/{index}",
                    defaults={"raw_relation": relation_type},
                )

    def _upsert_producer(self, item: dict, *, observation) -> Contributor | None:
        external_id = item.get("id")
        if not isinstance(external_id, str):
            return None
        record = source_record_service.ensure_record(
            namespace_spec=VNDB_PRODUCER_NAMESPACE,
            external_id=external_id,
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://vndb.org/{external_id}",
        )
        contributor = self._get_or_create_contributor(
            record=record,
            kind=Contributor.Kind.ORGANIZATION,
        )
        self._simple_names(
            entity=contributor.entity,
            record=record,
            observation=observation,
            data=item,
        )
        self._upsert_external_links(
            entity=contributor.entity,
            record=record,
            observation=observation,
            data=item,
        )
        return contributor

    def _import_staff_credits(
        self,
        *,
        work: Work,
        observation,
        items: tuple[dict, ...],
    ) -> None:
        for item in items:
            contributor = self._upsert_embedded_staff(item, observation=observation)
            role = item.get("role")
            if contributor is None or not isinstance(role, str) or not role:
                continue
            credited_as = self._credited_name(item)
            self._bind_staff_alias(
                entity=contributor.entity,
                aid=item.get("aid"),
                name=item.get("name"),
                latin=None,
                observation=observation,
            )
            Credit.objects.get_or_create(
                work=work,
                contributor=contributor,
                role=role,
                credited_as=credited_as,
                observation=observation,
            )

    def _import_voice_performances(
        self,
        *,
        work: Work,
        observation,
        items: tuple[dict, ...],
    ) -> None:
        for item in items:
            staff_data = item.get("staff")
            character_data = item.get("character")
            if not isinstance(staff_data, dict) or not isinstance(character_data, dict):
                continue
            contributor = self._upsert_embedded_staff(
                staff_data, observation=observation
            )
            character_entity = self._upsert_embedded_character(
                character_data, observation=observation
            )
            if contributor is None or character_entity is None:
                continue
            self._bind_staff_alias(
                entity=contributor.entity,
                aid=staff_data.get("aid"),
                name=staff_data.get("name"),
                latin=None,
                observation=observation,
            )
            appearance = (
                current_appearances()
                .filter(
                    work=work,
                    character_entity=character_entity,
                )
                .order_by("id")
                .first()
            )
            if appearance is None:
                appearance = Appearance.objects.create(
                    work=work,
                    character_entity=character_entity,
                    role="",
                    observation=observation,
                )
            VoicePerformance.objects.get_or_create(
                appearance=appearance,
                contributor=contributor,
                language=staff_data.get("lang") or "",
                observation=observation,
                defaults={"credited_as": self._credited_name(staff_data)},
            )

    def _import_relations(
        self,
        *,
        entity: Entity,
        observation,
        items: tuple[dict, ...],
    ) -> None:
        for index, item in enumerate(items):
            target = self._upsert_related_work(item, observation=observation)
            if target is None or target.pk == entity.pk:
                continue
            raw_relation = item.get("relation")
            relation_type = self._relation_type(raw_relation)
            relation, _ = EntityRelation.objects.get_or_create(
                from_entity=entity,
                to_entity=target,
                relation_type=relation_type,
                defaults={
                    "qualifiers": {
                        "official": bool(item.get("relation_official")),
                    }
                },
            )
            EntityRelationEvidence.objects.get_or_create(
                relation=relation,
                observation=observation,
                json_pointer=f"/relations/{index}",
                defaults={"raw_relation": str(raw_relation or "")[:256]},
            )

    def _upsert_related_work(self, item: dict, *, observation) -> Entity | None:
        external_id = item.get("id")
        if not isinstance(external_id, str):
            return None
        record = source_record_service.ensure_record(
            namespace_spec=VNDB_VN_NAMESPACE,
            external_id=external_id,
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://vndb.org/{external_id}",
        )
        entity = self._get_or_create_entity(
            record=record,
            kind=Entity.Kind.WORK,
        )
        Work.objects.get_or_create(
            entity=entity,
            defaults={"work_type": Work.WorkType.GALGAME},
        )
        self._simple_names(
            entity=entity, record=record, observation=observation, data=item
        )
        return entity

    def _upsert_embedded_staff(self, item: dict, *, observation) -> Contributor | None:
        external_id = item.get("id")
        if not isinstance(external_id, str):
            return None
        record = source_record_service.ensure_record(
            namespace_spec=VNDB_STAFF_NAMESPACE,
            external_id=external_id,
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://vndb.org/{external_id}",
        )
        contributor = self._get_or_create_contributor(
            record=record,
            kind=Contributor.Kind.PERSON,
        )
        self._simple_names(
            entity=contributor.entity,
            record=record,
            observation=observation,
            data=item,
        )
        return contributor

    def _upsert_embedded_character(self, item: dict, *, observation) -> Entity | None:
        external_id = item.get("id")
        if not isinstance(external_id, str):
            return None
        record = source_record_service.ensure_record(
            namespace_spec=VNDB_CHARACTER_NAMESPACE,
            external_id=external_id,
            origin=ProviderRecord.Origin.API,
            canonical_url=f"https://vndb.org/{external_id}",
        )
        entity = self._get_or_create_entity(
            record=record,
            kind=Entity.Kind.CHARACTER,
        )
        self._simple_names(
            entity=entity, record=record, observation=observation, data=item
        )
        return entity

    @staticmethod
    def _get_or_create_entity(*, record: ProviderRecord, kind: str) -> Entity:
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record=record,
                mapping_kind=ProviderRepresentation.MappingKind.EXACT,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        if representation is not None:
            if representation.entity.kind != kind:
                raise ValueError(
                    f"Provider record {record} is already mapped to "
                    f"{representation.entity.kind}."
                )
            return representation.entity
        entity = Entity.objects.create(kind=kind)
        ProviderRepresentation.objects.create(
            provider_record=record,
            entity=entity,
            mapping_kind=ProviderRepresentation.MappingKind.EXACT,
            method=ProviderRepresentation.Method.PROVIDER,
            confidence=1,
        )
        return entity

    def _get_or_create_contributor(
        self,
        *,
        record: ProviderRecord,
        kind: str,
    ) -> Contributor:
        entity = self._get_or_create_entity(
            record=record,
            kind=Entity.Kind.CONTRIBUTOR,
        )
        contributor, _ = Contributor.objects.update_or_create(
            entity=entity,
            defaults={"kind": kind},
        )
        if kind == Contributor.Kind.PERSON:
            Person.objects.get_or_create(contributor=contributor)
        elif kind == Contributor.Kind.ORGANIZATION:
            Organization.objects.get_or_create(contributor=contributor)
        return contributor

    def _upsert_staff_aliases(
        self,
        *,
        entity: Entity,
        staff_record: ProviderRecord,
        observation,
        aliases: tuple[dict, ...],
    ) -> None:
        for item in aliases:
            self._bind_staff_alias(
                entity=entity,
                aid=item.get("aid"),
                name=item.get("name"),
                latin=item.get("latin"),
                staff_record=staff_record,
                observation=observation,
            )

    def _bind_staff_alias(
        self,
        *,
        entity: Entity,
        aid,
        name,
        latin,
        observation,
        staff_record: ProviderRecord | None = None,
    ) -> None:
        if not isinstance(aid, int) or isinstance(aid, bool):
            return
        record = source_record_service.ensure_record(
            namespace_spec=VNDB_STAFF_ALIAS_NAMESPACE,
            external_id=str(aid),
            origin=ProviderRecord.Origin.API,
            canonical_url=staff_record.canonical_url if staff_record else "",
        )
        ProviderRepresentation.objects.update_or_create(
            provider_record=record,
            entity=entity,
            mapping_kind=ProviderRepresentation.MappingKind.VARIANT,
            defaults={
                "method": ProviderRepresentation.Method.PROVIDER,
                "confidence": 1,
                "is_active": True,
            },
        )
        for value, kind in (
            (name, EntityName.Kind.ALIAS),
            (latin, EntityName.Kind.ROMANIZED),
        ):
            if isinstance(value, str) and value:
                EntityName.objects.get_or_create(
                    entity=entity,
                    provider_record=record,
                    observation=observation,
                    text=value,
                    language="",
                    kind=kind,
                )

    def _upsert_traits(
        self,
        *,
        entity: Entity,
        observation,
        items: tuple[dict, ...],
    ) -> None:
        taxonomy, _ = Taxonomy.objects.get_or_create(
            slug="vndb-traits",
            defaults={"name": "VNDB Character Traits"},
        )
        for index, item in enumerate(items):
            trait_id = item.get("id")
            name = item.get("name")
            if not isinstance(trait_id, str) or not isinstance(name, str):
                continue
            record = source_record_service.ensure_record(
                namespace_spec=VNDB_TRAIT_NAMESPACE,
                external_id=trait_id,
                origin=ProviderRecord.Origin.API,
                canonical_url=f"https://vndb.org/{trait_id}",
            )
            parent = self._trait_group(taxonomy=taxonomy, item=item)
            term, _ = Term.objects.update_or_create(
                taxonomy=taxonomy,
                slug=trait_id,
                defaults={"parent": parent},
            )
            TermLabel.objects.get_or_create(
                term=term,
                language="en",
                script="Latn",
                text=name,
                defaults={"is_preferred": True},
            )
            TermMapping.objects.get_or_create(term=term, provider_record=record)
            spoiler_level = self._bounded_spoiler_level(item.get("spoiler"))
            EntityTerm.objects.get_or_create(
                entity=entity,
                term=term,
                observation=observation,
                defaults={"spoiler_level": spoiler_level},
            )
            if item.get("lie"):
                knowledge_ingestion_service.record_fact(
                    entity=entity,
                    observation=observation,
                    slug="vndb-trait-lie",
                    name="VNDB Trait Lie",
                    value={"trait_id": trait_id, "lie": True},
                    value_type=Predicate.ValueType.JSON,
                    json_pointer=f"/traits/{index}/lie",
                    spoiler_level=spoiler_level,
                )

    @staticmethod
    def _trait_group(*, taxonomy: Taxonomy, item: dict) -> Term | None:
        group_id = item.get("group_id")
        group_name = item.get("group_name")
        if not isinstance(group_id, str) or not group_id:
            return None
        parent, _ = Term.objects.get_or_create(
            taxonomy=taxonomy,
            slug=f"group-{group_id}",
        )
        if isinstance(group_name, str) and group_name:
            TermLabel.objects.get_or_create(
                term=parent,
                language="en",
                script="Latn",
                text=group_name,
                defaults={"is_preferred": True},
            )
        return parent

    @staticmethod
    def _upsert_external_links(*, entity, record, observation, data) -> None:
        for item in data.get("extlinks") or []:
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            label = item.get("label") if isinstance(item.get("label"), str) else ""
            ExternalLink.objects.update_or_create(
                entity=entity,
                url=url,
                provider_record=record,
                observation=observation,
                defaults={
                    "label": label[:128],
                    "link_type": slugify(label)[:64],
                },
            )

    @staticmethod
    def _upsert_screenshots(*, entity, record, observation, data) -> None:
        for index, image in enumerate(data.get("screenshots") or []):
            url = image.get("url")
            if not isinstance(url, str) or not url:
                continue
            asset, _ = MediaAsset.objects.update_or_create(
                url=url,
                provider_record=record,
                defaults={
                    "media_type": "image",
                    "safety": VNDBImportService._media_safety(image),
                },
            )
            EntityMedia.objects.get_or_create(
                entity=entity,
                asset=asset,
                purpose="screenshot",
                observation=observation,
                defaults={"sort_order": index},
            )

    @staticmethod
    def _record_optional_fact(
        *,
        entity,
        observation,
        data,
        field,
        slug,
        name,
        value_type=Predicate.ValueType.JSON,
        spoiler_level=0,
    ) -> None:
        value = data.get(field)
        if value is None or value == "" or value == [] or value == {}:
            return
        knowledge_ingestion_service.record_fact(
            entity=entity,
            observation=observation,
            slug=slug,
            name=name,
            value=value,
            value_type=value_type,
            json_pointer=f"/{field}",
            spoiler_level=spoiler_level,
        )

    def _upsert_work_facts(self, *, entity, observation, data) -> None:
        for field, slug, name, value_type in (
            (
                "released",
                "release-period",
                "Release Period",
                Predicate.ValueType.JSON,
            ),
            ("languages", "languages", "Languages", Predicate.ValueType.JSON),
            ("platforms", "platforms", "Platforms", Predicate.ValueType.JSON),
            (
                "length_votes",
                "playtime-votes",
                "Playtime Votes",
                Predicate.ValueType.NUMBER,
            ),
        ):
            if field == "released":
                start, end, precision = self._partial_date(data.get(field))
                value = {
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                    "precision": precision,
                    "raw_value": data.get(field),
                }
                if not data.get(field):
                    continue
                knowledge_ingestion_service.record_fact(
                    entity=entity,
                    observation=observation,
                    slug=slug,
                    name=name,
                    value=value,
                    value_type=value_type,
                    json_pointer=f"/{field}",
                )
                continue
            self._record_optional_fact(
                entity=entity,
                observation=observation,
                data=data,
                field=field,
                slug=slug,
                name=name,
                value_type=value_type,
            )

    def _upsert_release_facts(self, *, entity, observation, data) -> None:
        for field in (
            "languages",
            "media",
            "resolution",
            "voiced",
            "engine",
            "freeware",
            "uncensored",
        ):
            value_type = (
                Predicate.ValueType.BOOLEAN
                if isinstance(data.get(field), bool)
                else Predicate.ValueType.NUMBER
                if isinstance(data.get(field), (int, float))
                else Predicate.ValueType.STRING
                if isinstance(data.get(field), str)
                else Predicate.ValueType.JSON
            )
            self._record_optional_fact(
                entity=entity,
                observation=observation,
                data=data,
                field=field,
                slug=f"release-{field}",
                name=f"Release {field.replace('_', ' ').title()}",
                value_type=value_type,
            )

    def _upsert_character_facts(self, *, entity, observation, data) -> None:
        for field in (
            "blood_type",
            "height",
            "weight",
            "bust",
            "waist",
            "hips",
            "cup",
            "birthday",
            "age",
        ):
            value_type = (
                Predicate.ValueType.NUMBER
                if isinstance(data.get(field), (int, float))
                else Predicate.ValueType.STRING
                if isinstance(data.get(field), str)
                else Predicate.ValueType.JSON
            )
            self._record_optional_fact(
                entity=entity,
                observation=observation,
                data=data,
                field=field,
                slug=f"character-{field}",
                name=f"Character {field.replace('_', ' ').title()}",
                value_type=value_type,
            )
        for field in ("sex", "gender"):
            values = data.get(field)
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values[:2]):
                if value is None:
                    continue
                knowledge_ingestion_service.record_fact(
                    entity=entity,
                    observation=observation,
                    slug=f"character-{'actual-' if index else ''}{field}",
                    name=f"Character {'Actual ' if index else ''}{field.title()}",
                    value=value,
                    value_type=Predicate.ValueType.STRING,
                    json_pointer=f"/{field}/{index}",
                    spoiler_level=2 if index else 0,
                )

    @staticmethod
    def _upsert_names(*, entity, record, observation, data) -> None:
        titles = data.get("titles") or []
        if titles:
            for item in titles:
                title = item.get("title")
                if not isinstance(title, str) or not title:
                    continue
                language = item.get("lang") or ""
                is_original = language == (data.get("olang") or "")
                kind = (
                    EntityName.Kind.ORIGINAL
                    if is_original
                    else EntityName.Kind.OFFICIAL
                )
                EntityName.objects.get_or_create(
                    entity=entity,
                    provider_record=record,
                    observation=observation,
                    text=title,
                    language=language,
                    kind=kind,
                    defaults={
                        "is_original": is_original,
                        "is_official": bool(item.get("official")),
                    },
                )
                latin = item.get("latin")
                if isinstance(latin, str) and latin and latin != title:
                    EntityName.objects.get_or_create(
                        entity=entity,
                        provider_record=record,
                        observation=observation,
                        text=latin,
                        language=language,
                        kind=EntityName.Kind.ROMANIZED,
                    )
        for alias in data.get("aliases") or []:
            if isinstance(alias, str) and alias:
                EntityName.objects.get_or_create(
                    entity=entity,
                    provider_record=record,
                    observation=observation,
                    text=alias,
                    language="",
                    kind=EntityName.Kind.ALIAS,
                )
        VNDBImportService._simple_names(
            entity=entity,
            record=record,
            observation=observation,
            data=data,
        )

    @staticmethod
    def _simple_names(*, entity, record, observation, data) -> None:
        for key, kind, original in (
            ("title", EntityName.Kind.OFFICIAL, False),
            ("name", EntityName.Kind.OFFICIAL, False),
            ("alttitle", EntityName.Kind.ORIGINAL, True),
            ("original", EntityName.Kind.ORIGINAL, True),
        ):
            value = data.get(key)
            if isinstance(value, str) and value:
                EntityName.objects.get_or_create(
                    entity=entity,
                    provider_record=record,
                    observation=observation,
                    text=value,
                    language=data.get("olang") or data.get("lang") or "",
                    kind=kind,
                    defaults={"is_original": original, "is_official": not original},
                )

    @staticmethod
    def _upsert_description(*, entity, record, observation, data) -> None:
        value = data.get("description")
        if isinstance(value, str) and value:
            EntityDescription.objects.update_or_create(
                entity=entity,
                language="",
                provider_record=record,
                observation=observation,
                defaults={"text": value},
            )

    @staticmethod
    def _upsert_image(*, entity, record, observation, data) -> None:
        image = data.get("image") or {}
        url = image.get("url")
        if not isinstance(url, str) or not url:
            return
        asset, _ = MediaAsset.objects.update_or_create(
            url=url,
            provider_record=record,
            defaults={
                "media_type": "image",
                "safety": VNDBImportService._media_safety(image),
            },
        )
        EntityMedia.objects.get_or_create(
            entity=entity,
            asset=asset,
            purpose="poster",
            observation=observation,
        )

    @staticmethod
    def _upsert_metrics(*, entity, record, data) -> None:
        for metric, raw in (
            ("score", data.get("rating")),
            ("votes", data.get("votecount")),
        ):
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, TypeError, ValueError):
                continue
            MetricSnapshot.objects.get_or_create(
                entity=entity,
                provider_record=record,
                metric=metric,
                value=value,
                observed_at=record.latest_revision.fetched_at,
            )

    def _upsert_tags(self, *, entity, observation, data) -> None:
        taxonomy, _ = Taxonomy.objects.get_or_create(
            slug="vndb-tags", defaults={"name": "VNDB Tags"}
        )
        for item in data.get("tags") or []:
            tag_id = item.get("id")
            name = item.get("name")
            if not isinstance(tag_id, str) or not isinstance(name, str):
                continue
            record = source_record_service.ensure_record(
                namespace_spec=VNDB_TAG_NAMESPACE,
                external_id=tag_id,
                origin=ProviderRecord.Origin.API,
                canonical_url=f"https://vndb.org/g{tag_id.lstrip('g')}",
            )
            term, _ = Term.objects.get_or_create(taxonomy=taxonomy, slug=tag_id)
            TermLabel.objects.get_or_create(
                term=term,
                language="en",
                script="Latn",
                text=name,
                defaults={"is_preferred": True},
            )
            TermMapping.objects.get_or_create(term=term, provider_record=record)
            EntityTerm.objects.get_or_create(
                entity=entity,
                term=term,
                observation=observation,
                defaults={
                    "relevance": Decimal(str(item.get("rating") or 1)),
                    "spoiler_level": min(int(item.get("spoiler") or 0), 3),
                },
            )

    @staticmethod
    def _positive_int(value, *, default=None):
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            else default
        )

    @staticmethod
    def _partial_date(value):
        if not isinstance(value, str) or not value or value.upper() == "TBA":
            return None, None, Release.DatePrecision.UNKNOWN
        parts = value.split("-")
        try:
            if len(parts) == 1 and len(parts[0]) == 4:
                year = int(parts[0])
                return (
                    date(year, 1, 1),
                    date(year, 12, 31),
                    Release.DatePrecision.YEAR,
                )
            if len(parts) == 2:
                year, month = (int(part) for part in parts)
                return (
                    date(year, month, 1),
                    date(year, month, monthrange(year, month)[1]),
                    Release.DatePrecision.MONTH,
                )
        except (TypeError, ValueError):
            return None, None, Release.DatePrecision.UNKNOWN
        try:
            parsed = date.fromisoformat(value)
            return parsed, parsed, Release.DatePrecision.DAY
        except ValueError:
            return None, None, Release.DatePrecision.UNKNOWN

    @staticmethod
    def _bounded_spoiler_level(value) -> int:
        return min(max(value, 0), 3) if isinstance(value, int) else 0

    @staticmethod
    def _credited_name(data: dict) -> str:
        for key in ("name", "title", "original"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value[:512]
        return ""

    @staticmethod
    def _development_status(value) -> str:
        return {0: "finished", 1: "in-development", 2: "cancelled"}.get(value, "")

    @staticmethod
    def _media_safety(data: dict) -> str:
        sexual = data.get("sexual")
        if not isinstance(sexual, (int, float)):
            return MediaAsset.Safety.UNKNOWN
        if sexual >= 1.5:
            return MediaAsset.Safety.EXPLICIT
        if sexual > 0:
            return MediaAsset.Safety.SUGGESTIVE
        return MediaAsset.Safety.SAFE

    @staticmethod
    def _relation_type(value) -> str:
        return {
            "seq": "sequel",
            "preq": "prequel",
            "set": "same-setting",
            "alt": "alternate-version",
            "char": "shares-characters",
            "side": "side-story",
            "par": "parent-story",
            "ser": "same-series",
            "fan": "fandisc",
            "orig": "original-version",
        }.get(value, "related")

    @staticmethod
    def _release_work_role(value) -> str:
        return {
            "complete": ReleaseWork.Role.PRIMARY,
            "partial": ReleaseWork.Role.INCLUDED,
            "trial": ReleaseWork.Role.BONUS,
        }.get(value, ReleaseWork.Role.PRIMARY)

    @staticmethod
    def _audience_from_vn(data) -> str:
        image = data.get("image") or {}
        sexual = image.get("sexual")
        return (
            Entity.Audience.ADULT
            if isinstance(sexual, (int, float)) and sexual >= 1.5
            else Entity.Audience.UNKNOWN
        )


vndb_import_service = VNDBImportService()
