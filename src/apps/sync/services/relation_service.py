import uuid

from django.db import transaction
from django.db.models import Q

from apps.index.models import (
    Character,
    Staff,
    Subject,
    SubjectCharacterActorRelation,
    SubjectCharacterRelation,
    SubjectStaffRelation,
    SubjectSubjectRelation,
)
from apps.sync.providers.bangumi import BangumiAPIError, bangumi_client
from apps.sync.services.character_service import character_service
from apps.sync.services.name_normalizer import name_normalizer
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

        with transaction.atomic():
            source = Subject.objects.select_for_update().get(pk=source.pk)
            existing_relations = set(
                SubjectSubjectRelation.objects.filter(source=source).values_list(
                    "target_id", "relation"
                )
            )
            to_create = new_relations - existing_relations
            to_delete = existing_relations - new_relations
            if to_create:
                SubjectSubjectRelation.objects.bulk_create(
                    [
                        SubjectSubjectRelation(
                            source=source, target_id=target_id, relation=relation
                        )
                        for target_id, relation in to_create
                    ],
                )
            if to_delete:
                q = Q()
                for target_id, relation in to_delete:
                    q |= Q(target_id=target_id, relation=relation)
                SubjectSubjectRelation.objects.filter(source=source).filter(q).delete()

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

        with transaction.atomic():
            subject = Subject.objects.select_for_update().get(pk=subject.pk)
            existing_relations = set(
                SubjectStaffRelation.objects.filter(subject=subject).values_list(
                    "staff_id", "role"
                )
            )
            to_create = new_relations - existing_relations
            to_delete = existing_relations - new_relations
            if to_create:
                SubjectStaffRelation.objects.bulk_create(
                    [
                        SubjectStaffRelation(
                            subject=subject, staff_id=staff_id, role=role
                        )
                        for staff_id, role in to_create
                    ],
                )
            if to_delete:
                q = Q()
                for (
                    staff_id,
                    role,
                ) in to_delete:
                    q |= Q(staff_id=staff_id, role=role)
                SubjectStaffRelation.objects.filter(subject=subject).filter(q).delete()

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

        with transaction.atomic():
            subject = Subject.objects.select_for_update().get(pk=subject.pk)
            existing_char_relations = set(
                SubjectCharacterRelation.objects.filter(subject=subject).values_list(
                    "character_id", "role"
                )
            )
            to_create_char = new_char_relations - existing_char_relations
            to_delete_char = existing_char_relations - new_char_relations
            if to_create_char:
                SubjectCharacterRelation.objects.bulk_create(
                    [
                        SubjectCharacterRelation(
                            subject=subject, character_id=character_id, role=role
                        )
                        for character_id, role in to_create_char
                    ],
                )
            if to_delete_char:
                q = Q()
                for character_id, role in to_delete_char:
                    q |= Q(character_id=character_id, role=role)
                SubjectCharacterRelation.objects.filter(subject=subject).filter(
                    q
                ).delete()

            existing_actor_relations = set(
                SubjectCharacterActorRelation.objects.filter(
                    subject=subject
                ).values_list("character_id", "actor_id")
            )
            to_create_actor = new_actor_relations - existing_actor_relations
            to_delete_actor = existing_actor_relations - new_actor_relations
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
            if to_delete_actor:
                q = Q()
                for character_id, actor_id in to_delete_actor:
                    q |= Q(character_id=character_id, actor_id=actor_id)
                SubjectCharacterActorRelation.objects.filter(subject=subject).filter(
                    q
                ).delete()

        return {"characters": character_ids, "actors": actor_ids}

    def _map_subjects(self, ids: set[str]) -> dict[str, Subject]:
        if not ids:
            return {}

        existing = Subject.objects.filter(
            info_source=subject_service.INFO_SOURCE,
            id_source__in=ids,
        )

        mapping = {obj.id_source: obj for obj in existing}
        missing_ids = ids - set(mapping)
        if not missing_ids:
            return mapping

        for missing_id in sorted(missing_ids, key=int):
            obj = subject_service.provide_subject(missing_id)
            if obj:
                mapping[obj.id_source] = obj

        return mapping

    def _map_staff(self, ids: set[str]) -> dict[str, Staff]:
        if not ids:
            return {}

        existing = Staff.objects.filter(
            info_source=staff_service.INFO_SOURCE,
            id_source__in=ids,
        )
        mapping = {obj.id_source: obj for obj in existing}
        missing_ids = ids - set(mapping)

        if not missing_ids:
            return mapping
        for missing_id in sorted(missing_ids, key=int):
            obj = staff_service.provide_staff(missing_id)
            if obj:
                mapping[obj.id_source] = obj

        return mapping

    def _map_characters(self, ids: set[str]) -> dict[str, Character]:
        if not ids:
            return {}

        existing = Character.objects.filter(
            info_source=character_service.INFO_SOURCE,
            id_source__in=ids,
        )
        mapping = {obj.id_source: obj for obj in existing}
        missing_ids = ids - set(mapping)

        if not missing_ids:
            return mapping
        for missing_id in sorted(missing_ids, key=int):
            obj = character_service.provide_character(missing_id)
            if obj:
                mapping[obj.id_source] = obj

        return mapping


relation_service = RelationService()
