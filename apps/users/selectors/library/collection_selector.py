from django.db.models import Count

from apps.users.models import Collection, CollectionItem
from apps.users.exceptions import CollectionNotFound


class CollectionSelector:

    @staticmethod
    def base_queryset():
        return Collection.objects.select_related("user").annotate(
            item_count=Count("items", distinct=True)
        )

    @classmethod
    def list_my_collections(
        cls,
        *,
        user,
        keyword=None,
        ordering="id",
    ):
        qs = cls.base_queryset().filter(user=user)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(name__icontains=keyword)

        allowed_ordering = {
            "id",
            "-id",
            "name",
            "-name",
            "simple_rating",
            "-simple_rating",
            "item_count",
            "-item_count",
        }

        if ordering not in allowed_ordering:
            ordering = "id"

        return qs.order_by(ordering, "-id")

    @classmethod
    def get_my_collection(cls, *, user, collection_id: int):
        return cls.base_queryset().get(
            id=collection_id,
            user=user,
        )

    @classmethod
    def get_my_collection_or_raise(cls, *, user, collection_id: int):
        try:
            return cls.get_my_collection(
                user=user,
                collection_id=collection_id,
            )
        except Collection.DoesNotExist:
            raise CollectionNotFound()

    @staticmethod
    def list_collection_items(*, collection):
        return (
            CollectionItem.objects.select_related(
                "collection",
                "user_subject",
                "user_subject__subject",
            )
            .filter(collection=collection)
            .order_by("order", "id")
        )

    @staticmethod
    def get_collection_item(*, collection, item_id: int):
        return (
            CollectionItem.objects.select_related(
                "collection",
                "user_subject",
                "user_subject__subject",
            )
            .filter(
                collection=collection,
                id=item_id,
            )
            .first()
        )
