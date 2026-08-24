from django.db import transaction
from django.utils.text import slugify

from apps.index.models import (
    Appearance,
    Contributor,
    Credit,
    Entity,
    EntityRelation,
    EntityRelationEvidence,
    VoicePerformance,
    Work,
)
from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.bangumi import (
    BANGUMI_SUBJECT_CHARACTERS_NAMESPACE,
    BANGUMI_SUBJECT_RELATIONS_NAMESPACE,
    BANGUMI_SUBJECT_STAFF_NAMESPACE,
    BangumiAPIError,
    bangumi_client,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.character_service import character_service
from apps.sync.services.name_normalizer import name_normalizer
from apps.sync.services.source_record_service import source_record_service
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
                    from_entity=source,
                    to_entity=target,
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

        source = subject_service.provide_subject(bangumi_id)
        work = Work.objects.get(entity=source)
        staff_ids = {
            str(item.get("id"))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        staff_map = self._map_staff(staff_ids)

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
            for item in data:
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    continue
                staff = staff_map.get(str(item["id"]))
                if staff is None:
                    continue
                role = (
                    name_normalizer.normalize_name(item.get("relation") or "")
                    or "staff"
                )
                Credit.objects.get_or_create(
                    work=work,
                    contributor=staff,
                    role=role,
                    credited_as=str(item.get("name") or "")[:512],
                    observation=observation,
                )

        return staff_ids

    def upsert_character_relation(self, bangumi_id: int) -> dict:
        data = bangumi_client.fetch_subject_characters(bangumi_id)
        if not isinstance(data, list):
            raise BangumiAPIError("Bangumi character relation response must be a list.")

        source = subject_service.provide_subject(bangumi_id)
        work = Work.objects.get(entity=source)
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
            for item in data:
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    continue
                character = character_map.get(str(item["id"]))
                if character is None:
                    continue
                role = name_normalizer.normalize_name(item.get("relation") or "")
                appearance, _ = Appearance.objects.get_or_create(
                    work=work,
                    character_entity=character,
                    role=role,
                    observation=observation,
                )
                for actor_item in item.get("actors") or ():
                    if not isinstance(actor_item, dict) or not isinstance(
                        actor_item.get("id"), int
                    ):
                        continue
                    actor = actor_map.get(str(actor_item["id"]))
                    if actor is None:
                        continue
                    VoicePerformance.objects.get_or_create(
                        appearance=appearance,
                        contributor=actor,
                        language="",
                        observation=observation,
                        defaults={
                            "credited_as": str(actor_item.get("name") or "")[:512]
                        },
                    )

        return {"characters": character_ids, "actors": actor_ids}

    @staticmethod
    def _map_subjects(ids: set[str]) -> dict[str, Entity]:
        return {
            external_id: subject_service.provide_subject(external_id)
            for external_id in sorted(ids, key=int)
        }

    @staticmethod
    def _map_staff(ids: set[str]) -> dict[str, Contributor]:
        return {
            external_id: staff_service.provide_staff(external_id)
            for external_id in sorted(ids, key=int)
        }

    @staticmethod
    def _map_characters(ids: set[str]) -> dict[str, Entity]:
        return {
            external_id: character_service.provide_character(external_id)
            for external_id in sorted(ids, key=int)
        }


relation_service = RelationService()
