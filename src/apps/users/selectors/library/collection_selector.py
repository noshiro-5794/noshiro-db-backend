from django.db.models import Count, Exists, OuterRef, Q

from apps.community.models import CommunityBookmark, CommunityReaction
from apps.users.exceptions import CollectionNotFound
from apps.users.models import Collection, CollectionItem


class CollectionSelector:
    @staticmethod
    def base_queryset():
        return Collection.objects.select_related("user").annotate(
            item_count=Count("items", distinct=True),
            reaction_count=Count(
                "community_reactions",
                filter=Q(
                    community_reactions__reaction_type=CommunityReaction.ReactionType.LIKE
                ),
                distinct=True,
            ),
        )

    @staticmethod
    def _is_authenticated_user(user):
        return bool(user and getattr(user, "is_authenticated", False))

    @classmethod
    def _annotate_viewer_state(cls, qs, *, viewer=None):
        if not cls._is_authenticated_user(viewer):
            return qs

        return qs.annotate(
            viewer_has_liked=Exists(
                CommunityReaction.objects.filter(
                    user=viewer,
                    collection_id=OuterRef("pk"),
                    reaction_type=CommunityReaction.ReactionType.LIKE,
                )
            ),
            viewer_has_bookmarked=Exists(
                CommunityBookmark.objects.filter(
                    user=viewer,
                    collection_id=OuterRef("pk"),
                )
            ),
        )

    @classmethod
    def list_my_collections(
        cls,
        *,
        user,
        keyword=None,
        ordering="id",
    ):
        qs = cls._annotate_viewer_state(
            cls.base_queryset().filter(user=user), viewer=user
        )

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
        return cls._annotate_viewer_state(
            cls.base_queryset().filter(
                id=collection_id,
                user=user,
            ),
            viewer=user,
        ).get()

    @classmethod
    def get_my_collection_or_raise(cls, *, user, collection_id: int):
        try:
            return cls.get_my_collection(
                user=user,
                collection_id=collection_id,
            )
        except Collection.DoesNotExist as exc:
            raise CollectionNotFound() from exc

    @staticmethod
    def get_my_collection_for_update_or_raise(*, user, collection_id: int):
        try:
            return Collection.objects.select_for_update().get(
                id=collection_id,
                user=user,
            )
        except Collection.DoesNotExist as exc:
            raise CollectionNotFound() from exc

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
