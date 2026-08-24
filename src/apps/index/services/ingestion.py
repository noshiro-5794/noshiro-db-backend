import hashlib
import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.index.models import (
    AnimeProfile,
    ContentSafety,
    Contributor,
    CurrentObservation,
    Entity,
    EntityDescription,
    EntityMedia,
    EntityName,
    EntityRelation,
    EntityRelationEvidence,
    Fact,
    FactEvidence,
    GalgameProfile,
    IndexCollection,
    IndexMembership,
    MappingRun,
    MediaAsset,
    MetricSnapshot,
    Observation,
    Organization,
    Person,
    Predicate,
    ProviderRecord,
    ProviderRepresentation,
    Work,
)

from .identity import cross_provider_identity_service


class KnowledgeIngestionService:
    MAPPER_VERSION = "index-work-v1"
    LEGACY_NAMESPACE = uuid.UUID("90b60f43-99aa-4ac2-b9ec-16fe6ef70966")
    EPISODE_NAMESPACE = uuid.UUID("1e6aface-b51d-4cf9-b37a-7dd12beb2e2e")

    @staticmethod
    def _hash(data: Any) -> str:
        encoded = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @transaction.atomic
    def record_observation(
        self,
        *,
        provider_record: ProviderRecord,
        mapper: str,
        mapper_version: str,
        normalized_data: dict[str, Any],
        schema_name: str,
        schema_version: str,
    ) -> Observation:
        revision = provider_record.latest_revision
        normalized_hash = self._hash(normalized_data)
        if revision is None:
            observation, _ = Observation.objects.get_or_create(
                provider_record=provider_record,
                mapping_run=None,
                schema_name=schema_name,
                normalized_hash=normalized_hash,
                defaults={
                    "origin": Observation.Origin.LEGACY,
                    "schema_version": schema_version,
                    "normalized_data": normalized_data,
                },
            )
            self._select_current_observation(
                provider_record=provider_record,
                mapper=mapper,
                schema_name=schema_name,
                observation=observation,
            )
            return observation

        existing = Observation.objects.filter(
            provider_record=provider_record,
            mapping_run__revision=revision,
            mapping_run__mapper=mapper,
            mapping_run__mapper_version=mapper_version,
            mapping_run__status=MappingRun.Status.SUCCEEDED,
            schema_name=schema_name,
            normalized_hash=normalized_hash,
        ).first()
        if existing is not None:
            self._select_current_observation(
                provider_record=provider_record,
                mapper=mapper,
                schema_name=schema_name,
                observation=existing,
            )
            return existing

        mapping_run = MappingRun.objects.create(
            revision=revision,
            mapper=mapper,
            mapper_version=mapper_version,
            status=MappingRun.Status.RUNNING,
        )
        observation = Observation.objects.create(
            provider_record=provider_record,
            mapping_run=mapping_run,
            origin=Observation.Origin.MAPPED,
            schema_name=schema_name,
            schema_version=schema_version,
            normalized_data=normalized_data,
            normalized_hash=normalized_hash,
        )
        mapping_run.status = MappingRun.Status.SUCCEEDED
        mapping_run.finished_at = timezone.now()
        mapping_run.save(update_fields=["status", "finished_at", "updated_at"])
        self._select_current_observation(
            provider_record=provider_record,
            mapper=mapper,
            schema_name=schema_name,
            observation=observation,
        )
        return observation

    @staticmethod
    def _select_current_observation(
        *,
        provider_record: ProviderRecord,
        mapper: str,
        schema_name: str,
        observation: Observation,
    ) -> None:
        CurrentObservation.objects.update_or_create(
            provider_record=provider_record,
            mapper=mapper,
            schema_name=schema_name,
            defaults={"observation": observation},
        )

    @transaction.atomic
    def record_fact(
        self,
        *,
        entity: Entity,
        observation: Observation,
        slug: str,
        name: str,
        value: Any,
        value_type: str,
        json_pointer: str,
        language: str = "",
        spoiler_level: int = 0,
        safety: str = ContentSafety.UNKNOWN,
    ) -> Fact:
        predicate, created = Predicate.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "value_type": value_type},
        )
        if not created and predicate.value_type != value_type:
            raise ValueError(
                f"Predicate {slug} expects {predicate.value_type}, not {value_type}."
            )
        value_hash = self._hash(value)
        fact, _ = Fact.objects.get_or_create(
            entity=entity,
            predicate=predicate,
            value_hash=value_hash,
            language=language,
            defaults={
                "value": value,
                "spoiler_level": spoiler_level,
                "safety": safety,
            },
        )
        FactEvidence.objects.get_or_create(
            fact=fact,
            observation=observation,
            json_pointer=json_pointer,
        )
        from .fact_resolution import fact_resolution_service

        fact_resolution_service.rebuild(
            entity=entity,
            predicate=predicate,
            language=language,
        )
        return fact

    @transaction.atomic
    def project_work_from_record(
        self,
        *,
        provider_record: ProviderRecord,
        normalized_data: dict[str, Any],
        mapped_data: dict[str, Any],
        mapper_version: str,
        representation_method: str = ProviderRepresentation.Method.PROVIDER,
    ) -> Entity:
        observation = self.record_observation(
            provider_record=provider_record,
            mapper="bangumi.subject",
            mapper_version=mapper_version,
            normalized_data=normalized_data,
            schema_name="index.work",
            schema_version="1",
        )
        nsfw = bool(mapped_data.get("nsfw"))
        entity = self._resolve_or_create_entity(
            provider_record=provider_record,
            kind=Entity.Kind.WORK,
            audience=Entity.Audience.ADULT if nsfw else Entity.Audience.GENERAL,
        )
        work_type = self._work_type(mapped_data.get("subject_type"))
        work, _ = Work.objects.update_or_create(
            entity=entity,
            defaults={"work_type": work_type},
        )
        if work_type == Work.WorkType.ANIME:
            AnimeProfile.objects.update_or_create(
                work=work,
                defaults={
                    "episode_count": mapped_data.get("total_episodes")
                    or mapped_data.get("eps")
                },
            )
        elif work_type == Work.WorkType.GALGAME:
            GalgameProfile.objects.get_or_create(work=work)

        self._upsert_provider_representation(
            provider_record=provider_record,
            entity=entity,
            representation_method=representation_method,
        )
        self._replace_provider_names(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            original=mapped_data.get("title", ""),
            localized=mapped_data.get("title_cn", ""),
        )
        self._upsert_description(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            text=mapped_data.get("description", ""),
        )
        self._upsert_media(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            original=mapped_data.get("image_original", ""),
            thumbnail=mapped_data.get("image_thumbnail", ""),
        )
        self._sync_membership(entity=entity, work_type=work_type)
        self._record_mapped_work_facts(
            entity=entity,
            mapped_data=mapped_data,
            observation=observation,
        )
        self._record_bangumi_metrics(
            entity=entity,
            provider_record=provider_record,
            payload=normalized_data,
        )
        cross_provider_identity_service.observe_bangumi_work(
            entity=entity,
            observation=observation,
            payload=normalized_data,
        )
        return entity

    @transaction.atomic
    def project_character_from_record(
        self,
        *,
        provider_record: ProviderRecord,
        normalized_data: dict[str, Any],
        mapped_data: dict[str, Any],
        mapper: str,
        mapper_version: str,
        representation_method: str = ProviderRepresentation.Method.PROVIDER,
    ) -> Entity:
        observation = self.record_observation(
            provider_record=provider_record,
            mapper=mapper,
            mapper_version=mapper_version,
            normalized_data=normalized_data,
            schema_name="index.character",
            schema_version="1",
        )
        entity = self._resolve_or_create_entity(
            provider_record=provider_record,
            kind=Entity.Kind.CHARACTER,
            audience=Entity.Audience.UNKNOWN,
        )
        self._upsert_provider_representation(
            provider_record=provider_record,
            entity=entity,
            representation_method=representation_method,
        )
        self._replace_provider_names(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            original=mapped_data.get("name", ""),
        )
        self._upsert_description(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            text=mapped_data.get("description", ""),
        )
        self._upsert_media(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            original=mapped_data.get("image_original", ""),
            thumbnail=mapped_data.get("image_thumbnail", ""),
        )
        return entity

    @transaction.atomic
    def project_contributor_from_record(
        self,
        *,
        provider_record: ProviderRecord,
        normalized_data: dict[str, Any],
        mapped_data: dict[str, Any],
        mapper: str,
        mapper_version: str,
        representation_method: str = ProviderRepresentation.Method.PROVIDER,
    ) -> Contributor:
        observation = self.record_observation(
            provider_record=provider_record,
            mapper=mapper,
            mapper_version=mapper_version,
            normalized_data=normalized_data,
            schema_name="index.contributor",
            schema_version="1",
        )
        entity = self._resolve_or_create_entity(
            provider_record=provider_record,
            kind=Entity.Kind.CONTRIBUTOR,
            audience=Entity.Audience.UNKNOWN,
        )
        kind = self._contributor_kind(mapped_data.get("type"))
        contributor, _ = Contributor.objects.update_or_create(
            entity=entity,
            defaults={"kind": kind},
        )
        self._sync_contributor_subtype(contributor)
        self._upsert_provider_representation(
            provider_record=provider_record,
            entity=entity,
            representation_method=representation_method,
        )
        self._replace_provider_names(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            original=mapped_data.get("name", ""),
        )
        self._upsert_description(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            text=mapped_data.get("description", ""),
        )
        return contributor

    @transaction.atomic
    def project_episode_from_record(
        self,
        *,
        parent_entity: Entity,
        provider_record: ProviderRecord,
        normalized_data: dict[str, Any],
        mapped_data: dict[str, Any],
        relationship_observation: Observation,
        relationship_json_pointer: str,
        mapper_version: str,
        representation_method: str = ProviderRepresentation.Method.PROVIDER,
    ) -> Entity:
        observation = self.record_observation(
            provider_record=provider_record,
            mapper="bangumi.episode",
            mapper_version=mapper_version,
            normalized_data=normalized_data,
            schema_name="index.episode",
            schema_version="1",
        )
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record=provider_record,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        if representation is not None:
            entity = representation.entity
        else:
            entity, created = Entity.objects.get_or_create(
                id=uuid.uuid5(
                    self.EPISODE_NAMESPACE,
                    f"episode:{provider_record.external_id}",
                ),
                defaults={
                    "kind": Entity.Kind.EPISODE,
                    "audience": parent_entity.audience,
                },
            )
            if not created and entity.kind != Entity.Kind.EPISODE:
                raise ValueError(
                    f"Episode {provider_record.external_id} entity UUID collides "
                    f"with {entity.kind}."
                )
        if (
            parent_entity.audience == Entity.Audience.ADULT
            and entity.audience != Entity.Audience.ADULT
        ):
            entity.audience = Entity.Audience.ADULT
            entity.save(update_fields=["audience", "updated_at"])
        self._upsert_provider_representation(
            provider_record=provider_record,
            entity=entity,
            representation_method=representation_method,
        )
        self._replace_provider_names(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            original=mapped_data.get("title", ""),
            localized=mapped_data.get("title_cn", ""),
        )
        self._upsert_description(
            entity=entity,
            provider_record=provider_record,
            observation=observation,
            text=mapped_data.get("description", ""),
        )
        self._record_mapped_episode_facts(
            entity=entity,
            mapped_data=mapped_data,
            observation=observation,
        )
        relation, _ = EntityRelation.objects.get_or_create(
            from_entity=parent_entity,
            to_entity=entity,
            relation_type="has-episode",
        )
        EntityRelationEvidence.objects.get_or_create(
            relation=relation,
            observation=relationship_observation,
            json_pointer=relationship_json_pointer,
            defaults={"raw_relation": "has-episode"},
        )
        return entity

    def _record_mapped_episode_facts(
        self,
        *,
        entity: Entity,
        mapped_data: dict[str, Any],
        observation: Observation,
    ) -> None:
        duration = mapped_data.get("duration")
        candidates = {
            "episode-type": mapped_data.get("type") or None,
            "episode-number": mapped_data.get("ep_num"),
            "sort": mapped_data.get("sort"),
            "duration-seconds": duration.total_seconds() if duration else None,
            "air-date": mapped_data.get("date").isoformat()
            if mapped_data.get("date")
            else None,
            "disc": mapped_data.get("disc"),
            "comment-count": mapped_data.get("comment_count"),
            "raw-duration": mapped_data.get("raw_duration") or None,
        }
        for slug, value in candidates.items():
            if value is None:
                continue
            if isinstance(value, Decimal):
                value = str(value)
            value_type = Predicate.ValueType.JSON
            if isinstance(value, bool):
                value_type = Predicate.ValueType.BOOLEAN
            elif isinstance(value, (int, float)):
                value_type = Predicate.ValueType.NUMBER
            elif isinstance(value, str):
                value_type = Predicate.ValueType.STRING
            self.record_fact(
                entity=entity,
                observation=observation,
                slug=slug,
                name=slug.replace("-", " ").title(),
                value=value,
                value_type=value_type,
                json_pointer=f"/{slugify(slug)}",
            )

    @staticmethod
    def _resolve_or_create_entity(
        *,
        provider_record: ProviderRecord,
        kind: str,
        audience: str,
    ) -> Entity:
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record=provider_record,
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        if representation is not None:
            entity = representation.entity
            update_fields = []
            if entity.kind != kind:
                entity.kind = kind
                update_fields.append("kind")
            if entity.audience != audience:
                entity.audience = audience
                update_fields.append("audience")
            if update_fields:
                update_fields.append("updated_at")
                entity.save(update_fields=update_fields)
            return entity
        return Entity.objects.create(kind=kind, audience=audience)

    @staticmethod
    def _upsert_provider_representation(
        *,
        provider_record: ProviderRecord,
        entity: Entity,
        representation_method: str,
    ) -> None:
        ProviderRepresentation.objects.update_or_create(
            provider_record=provider_record,
            entity=entity,
            mapping_kind=ProviderRepresentation.MappingKind.EXACT,
            defaults={
                "method": representation_method,
                "confidence": Decimal("1"),
                "is_active": True,
            },
        )

    @staticmethod
    def _work_type(subject_type: str) -> str:
        return (
            subject_type
            if subject_type in Work.WorkType.values
            else Work.WorkType.OTHER
        )

    @staticmethod
    def _contributor_kind(staff_type: str) -> str:
        if staff_type == "Individual":
            return Contributor.Kind.PERSON
        if staff_type in {"Company", "Group"}:
            return Contributor.Kind.ORGANIZATION
        return Contributor.Kind.UNKNOWN

    @staticmethod
    def _sync_contributor_subtype(contributor: Contributor) -> None:
        if contributor.kind == Contributor.Kind.PERSON:
            Person.objects.get_or_create(contributor=contributor)
        elif contributor.kind == Contributor.Kind.ORGANIZATION:
            Organization.objects.get_or_create(contributor=contributor)

    @staticmethod
    def _replace_provider_names(
        *,
        entity: Entity,
        provider_record: ProviderRecord,
        observation: Observation,
        original: str,
        localized: str = "",
    ) -> None:
        names = []
        if original:
            names.append(
                EntityName(
                    entity=entity,
                    provider_record=provider_record,
                    observation=observation,
                    text=original,
                    kind=EntityName.Kind.ORIGINAL,
                    is_original=True,
                )
            )
        if localized and localized != original:
            names.append(
                EntityName(
                    entity=entity,
                    provider_record=provider_record,
                    observation=observation,
                    text=localized,
                    language="zh-Hans",
                    script="Hans",
                    kind=EntityName.Kind.TRANSLATED,
                )
            )
        EntityName.objects.bulk_create(names, ignore_conflicts=True)

    @staticmethod
    def _upsert_description(
        *,
        entity: Entity,
        provider_record: ProviderRecord,
        observation: Observation,
        text: str,
    ) -> None:
        if not text:
            return
        EntityDescription.objects.update_or_create(
            entity=entity,
            language="",
            provider_record=provider_record,
            observation=observation,
            defaults={"text": text},
        )

    @staticmethod
    def _upsert_media(
        *,
        entity: Entity,
        provider_record: ProviderRecord,
        observation: Observation,
        original: str,
        thumbnail: str,
    ) -> None:
        for purpose, url in (("poster", original), ("thumbnail", thumbnail)):
            if not url:
                continue
            asset, _ = MediaAsset.objects.get_or_create(
                url=url,
                provider_record=provider_record,
                defaults={"media_type": "image"},
            )
            EntityMedia.objects.get_or_create(
                entity=entity,
                asset=asset,
                purpose=purpose,
                observation=observation,
            )

    @staticmethod
    def _sync_membership(*, entity: Entity, work_type: str) -> None:
        if work_type not in {Work.WorkType.ANIME, Work.WorkType.GALGAME}:
            return
        collection, _ = IndexCollection.objects.get_or_create(
            slug=work_type,
            defaults={"name": work_type.capitalize()},
        )
        IndexMembership.objects.update_or_create(
            collection=collection,
            entity=entity,
            defaults={
                "listing_state": IndexMembership.State.LISTED,
                "inclusion_reason": "mapped work type",
            },
        )

    def _record_mapped_work_facts(
        self,
        *,
        entity: Entity,
        mapped_data: dict[str, Any],
        observation: Observation,
    ) -> None:
        release_date = mapped_data.get("date")
        candidates = {
            "release-date": release_date.isoformat() if release_date else None,
            "platform": mapped_data.get("platform") or None,
            "series": mapped_data.get("series"),
            "volumes": mapped_data.get("volumes"),
            "episode-count": mapped_data.get("total_episodes")
            or mapped_data.get("eps"),
            "provider-infobox": mapped_data.get("infobox") or None,
            "provider-tags": mapped_data.get("tags") or None,
        }
        for slug, value in candidates.items():
            if value is None:
                continue
            value_type = Predicate.ValueType.JSON
            if isinstance(value, bool):
                value_type = Predicate.ValueType.BOOLEAN
            elif isinstance(value, (int, float)):
                value_type = Predicate.ValueType.NUMBER
            elif isinstance(value, str):
                value_type = (
                    Predicate.ValueType.DATE
                    if slug == "release-date"
                    else Predicate.ValueType.STRING
                )
            self.record_fact(
                entity=entity,
                observation=observation,
                slug=slug,
                name=slug.replace("-", " ").title(),
                value=value,
                value_type=value_type,
                json_pointer=f"/{slugify(slug)}",
            )

    @staticmethod
    def _record_bangumi_metrics(
        *,
        entity: Entity,
        provider_record: ProviderRecord,
        payload: dict[str, Any],
    ) -> None:
        rating = payload.get("rating")
        if not isinstance(rating, dict):
            return
        for key, raw_value in (
            ("score", rating.get("score")),
            ("rank", rating.get("rank")),
            ("votes", rating.get("total")),
        ):
            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, TypeError, ValueError):
                continue
            MetricSnapshot.objects.get_or_create(
                entity=entity,
                provider_record=provider_record,
                metric=key,
                value=value,
                observed_at=provider_record.last_seen_at,
            )


knowledge_ingestion_service = KnowledgeIngestionService()
