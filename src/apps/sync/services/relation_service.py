import uuid

from django.db import transaction
from django.utils.text import slugify

from apps.index.models import (
    Appearance,
    CatalogSource,
    Character,
    Credit,
    EntityRelation,
    EntityRelationEvidence,
    RelationEvidence,
    Staff,
    Subject,
    SubjectCharacterActorRelation,
    SubjectCharacterRelation,
    SubjectStaffRelation,
    SubjectSubjectRelation,
    VoicePerformance,
)
from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.bangumi import (
    BANGUMI_CHARACTER_NAMESPACE,
    BANGUMI_PERSON_NAMESPACE,
    BANGUMI_SUBJECT_CHARACTERS_NAMESPACE,
    BANGUMI_SUBJECT_NAMESPACE,
    BANGUMI_SUBJECT_RELATIONS_NAMESPACE,
    BANGUMI_SUBJECT_STAFF_NAMESPACE,
    BangumiAPIError,
    bangumi_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.character_service import character_service
from apps.sync.services.name_normalizer import name_normalizer
from apps.sync.services.source_record_service import (
    source_identity_service,
    source_record_service,
)
from apps.sync.services.staff_service import staff_service
from apps.sync.services.subject_service import subject_service


class RelationService:
    def sync_all_relations(self, bangumi_id: int) -> dict:
        subject_ids = self.upsert_subject_relation(bangumi_id)
        staff_ids = self.upsert_staff_relation(bangumi_id)
        char_data = self.upsert_character_relation(bangumi_id)

        return {
            "subjects": subject_ids,
            "staffs": staff_ids.union(char_data["actors"]),
            "characters": char_data["characters"],
        }

    def upsert_subject_relation(self, bangumi_id: int) -> set[str]:
        data = bangumi_client.fetch_subject_subjects(bangumi_id)
        if not isinstance(data, list):
            raise BangumiAPIError("Bangumi subject relation response must be a list.")

        source = subject_service.provide_subject(bangumi_id)
        target_ids = {
            str(item.get("id"))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        target_map = self._map_subjects(target_ids)
        new_relations: set[tuple[uuid.UUID, str]] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            if not isinstance(raw_id, int):
                continue
            target = target_map.get(str(raw_id))
            if not target:
                continue
            relation = name_normalizer.normalize_name(item.get("relation") or "")
            new_relations.add((target.id, relation))

        catalog_source = self._get_bangumi_source()
        with transaction.atomic():
            source_record = source_record_service.record(
                namespace_spec=BANGUMI_SUBJECT_RELATIONS_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id=str(bangumi_id),
                    payload={"items": data},
                    canonical_url=f"https://bgm.tv/subject/{bangumi_id}/relations",
                    schema_version="bangumi-api-v0",
                    mapper_version="bangumi-subject-relations-v1",
                ),
            )
            observation = knowledge_ingestion_service.record_observation(
                provider_record=source_record.record,
                mapper="bangumi.subject-relations",
                mapper_version="bangumi-subject-relations-v1",
                normalized_data={"items": data},
                schema_name="index.work.relations",
                schema_version="1",
            )
            source = Subject.objects.select_for_update().get(pk=source.pk)
            existing_relations = set(
                SubjectSubjectRelation.objects.filter(source=source).values_list(
                    "target_id", "relation"
                )
            )
            to_create = new_relations - existing_relations
            if to_create:
                SubjectSubjectRelation.objects.bulk_create(
                    [
                        SubjectSubjectRelation(
                            source=source, target_id=target_id, relation=relation
                        )
                        for target_id, relation in to_create
                    ],
                )
            active_relation_ids = {
                relation.pk
                for relation in SubjectSubjectRelation.objects.filter(
                    source=source,
                    target_id__in={target_id for target_id, _relation in new_relations},
                )
                if (relation.target_id, relation.relation) in new_relations
            }
            self._replace_source_evidence(
                catalog_source=catalog_source,
                relation_model=SubjectSubjectRelation,
                evidence_field="subject_relation",
                evidence_scope={"subject_relation__source": source},
                active_relation_ids=active_relation_ids,
            )
            for index, item in enumerate(data):
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    continue
                target = target_map.get(str(item["id"]))
                if target is None:
                    continue
                relation_type = (
                    name_normalizer.normalize_name(item.get("relation") or "")
                    or "related"
                )
                relation_type = slugify(relation_type)[:128] or "related"
                relation, _ = EntityRelation.objects.get_or_create(
                    from_entity_id=source.pk,
                    to_entity_id=target.pk,
                    relation_type=relation_type,
                )
                EntityRelationEvidence.objects.get_or_create(
                    relation=relation,
                    observation=observation,
                    json_pointer=f"/items/{index}",
                    defaults={"raw_relation": str(item.get("relation") or "")[:256]},
                )

        return target_ids

    def upsert_staff_relation(self, bangumi_id: int) -> set[str]:
        data = bangumi_client.fetch_subject_persons(bangumi_id)
        if not isinstance(data, list):
            raise BangumiAPIError("Bangumi staff relation response must be a list.")

        subject = subject_service.provide_subject(bangumi_id)
        staff_ids = {
            str(item.get("id"))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        staff_map = self._map_staff(staff_ids)
        new_relations: set[tuple[int, str]] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            if not isinstance(raw_id, int):
                continue
            staff = staff_map.get(str(raw_id))
            if not isinstance(staff, Staff):
                continue
            role = name_normalizer.normalize_name(item.get("relation") or "")
            new_relations.add((staff.id, role))

        catalog_source = self._get_bangumi_source()
        with transaction.atomic():
            source_record = source_record_service.record(
                namespace_spec=BANGUMI_SUBJECT_STAFF_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id=str(bangumi_id),
                    payload={"items": data},
                    canonical_url=f"https://bgm.tv/subject/{bangumi_id}/staff",
                    schema_version="bangumi-api-v0",
                    mapper_version="bangumi-subject-staff-v1",
                ),
            )
            observation = knowledge_ingestion_service.record_observation(
                provider_record=source_record.record,
                mapper="bangumi.subject-staff",
                mapper_version="bangumi-subject-staff-v1",
                normalized_data={"items": data},
                schema_name="index.work.credits",
                schema_version="1",
            )
            subject = Subject.objects.select_for_update().get(pk=subject.pk)
            existing_relations = set(
                SubjectStaffRelation.objects.filter(subject=subject).values_list(
                    "staff_id", "role"
                )
            )
            to_create = new_relations - existing_relations
            if to_create:
                SubjectStaffRelation.objects.bulk_create(
                    [
                        SubjectStaffRelation(
                            subject=subject, staff_id=staff_id, role=role
                        )
                        for staff_id, role in to_create
                    ],
                )
            active_relation_ids = {
                relation.pk
                for relation in SubjectStaffRelation.objects.filter(
                    subject=subject,
                    staff_id__in={staff_id for staff_id, _role in new_relations},
                )
                if (relation.staff_id, relation.role) in new_relations
            }
            self._replace_source_evidence(
                catalog_source=catalog_source,
                relation_model=SubjectStaffRelation,
                evidence_field="staff_relation",
                evidence_scope={"staff_relation__subject": subject},
                active_relation_ids=active_relation_ids,
            )
            for item in data:
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    continue
                staff = staff_map.get(str(item["id"]))
                if staff is None or staff.contributor_id is None:
                    continue
                role = (
                    name_normalizer.normalize_name(item.get("relation") or "")
                    or "staff"
                )
                Credit.objects.get_or_create(
                    work_id=subject.pk,
                    contributor_id=staff.contributor_id,
                    role=role,
                    credited_as=str(item.get("name") or "")[:512],
                    observation=observation,
                )

        return staff_ids

    def upsert_character_relation(self, bangumi_id: int) -> dict:
        data = bangumi_client.fetch_subject_characters(bangumi_id)
        if not isinstance(data, list):
            raise BangumiAPIError("Bangumi character relation response must be a list.")

        subject = subject_service.provide_subject(bangumi_id)
        character_ids = {
            str(item.get("id"))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        character_map = self._map_characters(character_ids)
        actor_ids = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            actors = item.get("actors")
            if not isinstance(actors, list):
                continue
            for actor in actors:
                if isinstance(actor, dict) and isinstance(actor.get("id"), int):
                    actor_ids.add(str(actor.get("id")))
        actor_map = self._map_staff(actor_ids)
        new_char_relations: set[tuple[int, str]] = set()
        new_actor_relations: set[tuple[int, int]] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_char_id = item.get("id")
            if not isinstance(raw_char_id, int):
                continue
            character = character_map.get(str(raw_char_id))
            if not isinstance(character, Character):
                continue
            role = name_normalizer.normalize_name(item.get("relation") or "")
            new_char_relations.add((character.id, role))

            actors = item.get("actors")
            if not isinstance(actors, list):
                continue
            for actor_item in actors:
                if not isinstance(actor_item, dict):
                    continue
                raw_actor_id = actor_item.get("id")
                if not isinstance(raw_actor_id, int):
                    continue
                actor = actor_map.get(str(raw_actor_id))
                if not isinstance(actor, Staff):
                    continue
                new_actor_relations.add((character.id, actor.id))

        catalog_source = self._get_bangumi_source()
        with transaction.atomic():
            source_record = source_record_service.record(
                namespace_spec=BANGUMI_SUBJECT_CHARACTERS_NAMESPACE,
                fetched=FetchedSourceRecord(
                    external_id=str(bangumi_id),
                    payload={"items": data},
                    canonical_url=f"https://bgm.tv/subject/{bangumi_id}/characters",
                    schema_version="bangumi-api-v0",
                    mapper_version="bangumi-subject-characters-v1",
                ),
            )
            observation = knowledge_ingestion_service.record_observation(
                provider_record=source_record.record,
                mapper="bangumi.subject-characters",
                mapper_version="bangumi-subject-characters-v1",
                normalized_data={"items": data},
                schema_name="index.work.characters",
                schema_version="1",
            )
            subject = Subject.objects.select_for_update().get(pk=subject.pk)
            existing_char_relations = set(
                SubjectCharacterRelation.objects.filter(subject=subject).values_list(
                    "character_id", "role"
                )
            )
            to_create_char = new_char_relations - existing_char_relations
            if to_create_char:
                SubjectCharacterRelation.objects.bulk_create(
                    [
                        SubjectCharacterRelation(
                            subject=subject, character_id=character_id, role=role
                        )
                        for character_id, role in to_create_char
                    ],
                )
            active_character_relation_ids = {
                relation.pk
                for relation in SubjectCharacterRelation.objects.filter(
                    subject=subject,
                    character_id__in={
                        character_id for character_id, _role in new_char_relations
                    },
                )
                if (relation.character_id, relation.role) in new_char_relations
            }
            self._replace_source_evidence(
                catalog_source=catalog_source,
                relation_model=SubjectCharacterRelation,
                evidence_field="character_relation",
                evidence_scope={"character_relation__subject": subject},
                active_relation_ids=active_character_relation_ids,
            )

            existing_actor_relations = set(
                SubjectCharacterActorRelation.objects.filter(
                    subject=subject
                ).values_list("character_id", "actor_id")
            )
            to_create_actor = new_actor_relations - existing_actor_relations
            if to_create_actor:
                SubjectCharacterActorRelation.objects.bulk_create(
                    [
                        SubjectCharacterActorRelation(
                            subject=subject,
                            character_id=character_id,
                            actor_id=actor_id,
                        )
                        for character_id, actor_id in to_create_actor
                    ],
                )
            active_actor_relation_ids = {
                relation.pk
                for relation in SubjectCharacterActorRelation.objects.filter(
                    subject=subject,
                    character_id__in={
                        character_id for character_id, _actor_id in new_actor_relations
                    },
                )
                if (relation.character_id, relation.actor_id) in new_actor_relations
            }
            self._replace_source_evidence(
                catalog_source=catalog_source,
                relation_model=SubjectCharacterActorRelation,
                evidence_field="character_actor_relation",
                evidence_scope={"character_actor_relation__subject": subject},
                active_relation_ids=active_actor_relation_ids,
            )
            for item in data:
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    continue
                character = character_map.get(str(item["id"]))
                if character is None or character.entity_id is None:
                    continue
                role = name_normalizer.normalize_name(item.get("relation") or "")
                appearance, _ = Appearance.objects.get_or_create(
                    work_id=subject.pk,
                    character_entity_id=character.entity_id,
                    role=role,
                    observation=observation,
                )
                for actor_item in item.get("actors") or ():
                    if not isinstance(actor_item, dict) or not isinstance(
                        actor_item.get("id"), int
                    ):
                        continue
                    actor = actor_map.get(str(actor_item["id"]))
                    if actor is None or actor.contributor_id is None:
                        continue
                    VoicePerformance.objects.get_or_create(
                        appearance=appearance,
                        contributor_id=actor.contributor_id,
                        language="",
                        observation=observation,
                        defaults={
                            "credited_as": str(actor_item.get("name") or "")[:512]
                        },
                    )

        return {"characters": character_ids, "actors": actor_ids}

    @staticmethod
    def _get_bangumi_source() -> CatalogSource:
        namespace = source_record_service.get_or_create_namespace(
            BANGUMI_SUBJECT_NAMESPACE
        )
        return namespace.provider

    @staticmethod
    def _replace_source_evidence(
        *,
        catalog_source: CatalogSource,
        relation_model,
        evidence_field: str,
        evidence_scope: dict,
        active_relation_ids: set[int],
    ) -> None:
        RelationEvidence.objects.bulk_create(
            [
                RelationEvidence(
                    source=catalog_source,
                    **{f"{evidence_field}_id": relation_id},
                )
                for relation_id in active_relation_ids
            ],
            ignore_conflicts=True,
        )

        stale_evidence = RelationEvidence.objects.filter(
            source=catalog_source,
            **evidence_scope,
        )
        if active_relation_ids:
            stale_evidence = stale_evidence.exclude(
                **{f"{evidence_field}_id__in": active_relation_ids}
            )

        relation_id_field = f"{evidence_field}_id"
        stale_relation_ids = list(
            stale_evidence.values_list(relation_id_field, flat=True)
        )
        if not stale_relation_ids:
            return

        list(
            relation_model.objects.select_for_update()
            .filter(pk__in=stale_relation_ids)
            .values_list("pk", flat=True)
        )
        stale_evidence.delete()
        relation_model.objects.filter(
            pk__in=stale_relation_ids,
            evidence__isnull=True,
        ).delete()

    def _map_subjects(self, ids: set[str]) -> dict[str, Subject]:
        if not ids:
            return {}

        mapping = source_identity_service.resolve_subjects(
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            external_ids=ids,
            legacy_source=subject_service.INFO_SOURCE,
        )
        for external_id in sorted(ids, key=int):
            obj = subject_service.provide_subject(external_id)
            if obj:
                mapping[external_id] = obj

        return mapping

    def _map_staff(self, ids: set[str]) -> dict[str, Staff]:
        if not ids:
            return {}

        mapping = source_identity_service.resolve_staff_members(
            namespace_spec=BANGUMI_PERSON_NAMESPACE,
            external_ids=ids,
            legacy_source=staff_service.INFO_SOURCE,
        )
        for external_id in sorted(ids, key=int):
            obj = staff_service.provide_staff(external_id)
            if obj:
                mapping[external_id] = obj

        return mapping

    def _map_characters(self, ids: set[str]) -> dict[str, Character]:
        if not ids:
            return {}

        mapping = source_identity_service.resolve_characters(
            namespace_spec=BANGUMI_CHARACTER_NAMESPACE,
            external_ids=ids,
            legacy_source=character_service.INFO_SOURCE,
        )
        for external_id in sorted(ids, key=int):
            obj = character_service.provide_character(external_id)
            if obj:
                mapping[external_id] = obj

        return mapping


relation_service = RelationService()
