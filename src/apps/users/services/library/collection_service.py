from django.db import transaction

from apps.community.services.activity_service import ActivityService
from apps.users.exceptions import (
    CollectionItemNotFound,
    InvalidUserSubjectIds,
    UserSubjectNotFound,
)
from apps.users.models import Collection, CollectionItem, UserSubject
from apps.users.selectors.library.collection_selector import CollectionSelector


class CollectionService:
    @staticmethod
    def _get_my_user_subject_or_raise(*, user, user_subject_id: int):
        user_subject = (
            UserSubject.objects.select_related("user", "entity")
            .filter(
                id=user_subject_id,
                user=user,
                entity__isnull=False,
            )
            .first()
        )

        if not user_subject:
            raise UserSubjectNotFound()

        return user_subject

    @staticmethod
    def _get_my_user_subject_by_subject_id_or_raise(*, user, subject_id):
        user_subject = (
            UserSubject.objects.select_related("user", "subject")
            .filter(
                user=user,
                subject_id=subject_id,
            )
            .first()
        )

        if not user_subject:
            raise UserSubjectNotFound()

        return user_subject

    @classmethod
    def _resolve_user_subject_or_raise(
        cls,
        *,
        user,
        user_subject_id=None,
        subject_id=None,
    ):
        if user_subject_id is not None:
            return cls._get_my_user_subject_or_raise(
                user=user,
                user_subject_id=user_subject_id,
            )

        return cls._get_my_user_subject_by_subject_id_or_raise(
            user=user,
            subject_id=subject_id,
        )

    @classmethod
    def _resolve_collection_item_payloads(cls, *, user, items):
        if not items:
            return []

        resolved_items = []
        seen_ids = set()
        duplicate_ids = []

        user_subject_ids = [
            item["user_subject_id"]
            for item in items
            if item.get("user_subject_id") is not None
        ]
        user_subject_map = {
            user_subject.id: user_subject
            for user_subject in UserSubject.objects.filter(
                user=user,
                id__in=user_subject_ids,
            )
        }

        for item in items:
            if item.get("user_subject_id") is not None:
                user_subject_id = item["user_subject_id"]
                user_subject = user_subject_map.get(user_subject_id)

                if not user_subject:
                    raise InvalidUserSubjectIds()
            else:
                user_subject = cls._get_my_user_subject_by_subject_id_or_raise(
                    user=user,
                    subject_id=item["subject_id"],
                )
                user_subject_id = user_subject.id

            if user_subject_id in seen_ids:
                duplicate_ids.append(user_subject_id)

            seen_ids.add(user_subject_id)
            resolved_items.append(
                {
                    **item,
                    "user_subject_id": user_subject_id,
                }
            )

        if duplicate_ids:
            raise InvalidUserSubjectIds()

        return resolved_items

    @staticmethod
    @transaction.atomic
    def create_collection(
        *,
        user,
        name: str,
        simple_rating=None,
        note: str = "",
        is_public: bool = True,
    ):
        collection = Collection.objects.create(
            user=user,
            name=name.strip(),
            simple_rating=simple_rating,
            note=note,
            is_public=is_public,
        )

        ActivityService.create_collection_created_activity(
            user=user,
            collection=collection,
        )

        return CollectionSelector.get_my_collection_or_raise(
            user=user,
            collection_id=collection.id,
        )

    @staticmethod
    @transaction.atomic
    def update_collection(
        *,
        user,
        collection_id: int,
        **fields,
    ):
        collection = CollectionSelector.get_my_collection_for_update_or_raise(
            user=user,
            collection_id=collection_id,
        )

        allowed_fields = {
            "name",
            "simple_rating",
            "note",
            "is_public",
        }

        update_fields = []

        for key, value in fields.items():
            if key not in allowed_fields:
                continue

            if key == "name":
                value = value.strip()

            setattr(collection, key, value)
            update_fields.append(key)

        if update_fields:
            collection.save(update_fields=update_fields)

        return CollectionSelector.get_my_collection_or_raise(
            user=user,
            collection_id=collection_id,
        )

    @staticmethod
    @transaction.atomic
    def delete_collection(*, user, collection_id: int):
        collection = CollectionSelector.get_my_collection_for_update_or_raise(
            user=user,
            collection_id=collection_id,
        )

        collection.delete()

    @classmethod
    @transaction.atomic
    def add_collection_item(
        cls,
        *,
        user,
        collection_id: int,
        user_subject_id: int | None = None,
        subject_id=None,
        order: int = 0,
        relation: str = "",
    ):
        collection = CollectionSelector.get_my_collection_for_update_or_raise(
            user=user,
            collection_id=collection_id,
        )

        user_subject = cls._resolve_user_subject_or_raise(
            user=user,
            user_subject_id=user_subject_id,
            subject_id=subject_id,
        )

        item, created = CollectionItem.objects.get_or_create(
            collection=collection,
            user_subject=user_subject,
            defaults={
                "order": order,
                "relation": relation,
            },
        )

        if not created:
            item.order = order
            item.relation = relation
            item.save(update_fields=["order", "relation"])

        item = (
            CollectionItem.objects.select_related(
                "collection",
                "user_subject",
                "user_subject__entity",
                "user_subject__entity__work",
            )
            .prefetch_related(
                "user_subject__entity__names",
                "user_subject__entity__media__asset",
                "user_subject__entity__index_memberships__collection",
            )
            .get(id=item.id)
        )

        if created:
            ActivityService.create_collection_item_added_activity(
                user=user,
                collection_item=item,
            )

        return item, created

    @classmethod
    @transaction.atomic
    def replace_collection_items(
        cls,
        *,
        user,
        collection_id: int,
        items,
    ):
        collection = CollectionSelector.get_my_collection_for_update_or_raise(
            user=user,
            collection_id=collection_id,
        )

        resolved_items = cls._resolve_collection_item_payloads(
            user=user,
            items=items,
        )

        CollectionItem.objects.filter(
            collection=collection,
        ).delete()

        CollectionItem.objects.bulk_create(
            [
                CollectionItem(
                    collection=collection,
                    user_subject_id=item["user_subject_id"],
                    order=item.get("order", index),
                    relation=item.get("relation", ""),
                )
                for index, item in enumerate(resolved_items)
            ]
        )

        return CollectionSelector.list_collection_items(
            collection=collection,
        )

    @staticmethod
    @transaction.atomic
    def update_collection_items(
        *,
        user,
        collection_id: int,
        items,
    ):
        collection = CollectionSelector.get_my_collection_for_update_or_raise(
            user=user,
            collection_id=collection_id,
        )

        item_ids = [item["id"] for item in items]
        existing_items = {
            item.id: item
            for item in CollectionItem.objects.select_for_update().filter(
                collection=collection,
                id__in=item_ids,
            )
        }

        if len(existing_items) != len(set(item_ids)):
            raise CollectionItemNotFound()

        for item_payload in items:
            item = existing_items[item_payload["id"]]
            update_fields = []

            if "order" in item_payload:
                item.order = item_payload["order"]
                update_fields.append("order")

            if "relation" in item_payload:
                item.relation = item_payload["relation"]
                update_fields.append("relation")

            if update_fields:
                item.save(update_fields=update_fields)

        return CollectionSelector.list_collection_items(
            collection=collection,
        )

    @staticmethod
    @transaction.atomic
    def delete_collection_item(
        *,
        user,
        collection_id: int,
        item_id: int,
    ):
        collection = CollectionSelector.get_my_collection_for_update_or_raise(
            user=user,
            collection_id=collection_id,
        )

        item = CollectionSelector.get_collection_item(
            collection=collection,
            item_id=item_id,
        )

        if not item:
            raise CollectionItemNotFound()

        item.delete()
