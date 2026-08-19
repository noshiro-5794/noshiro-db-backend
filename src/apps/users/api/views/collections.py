from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.index.selectors.projections import entity_summary
from apps.users.api.serializers.collections import (
    CollectionCreateRequestSerializer,
    CollectionListRequestSerializer,
    CollectionUpdateRequestSerializer,
)
from apps.users.api.serializers.contracts import (
    CollectionItemPatchSerializer,
    CollectionItemReplaceSerializer,
    CollectionItemSerializer,
    CollectionItemWriteSerializer,
    UserCollectionSerializer,
)
from apps.users.models import CollectionItem
from apps.users.selectors.library.collection_selector import CollectionSelector
from apps.users.services.library.collection_service import CollectionService
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


def collection_data(collection) -> dict:
    return {
        "id": collection.id,
        "name": collection.name,
        "simple_rating": collection.simple_rating,
        "note": collection.note,
        "is_public": collection.is_public,
        "item_count": collection.item_count,
        "reaction_count": collection.reaction_count,
        "viewer_state": {
            "has_liked": bool(getattr(collection, "viewer_has_liked", False)),
            "has_bookmarked": bool(getattr(collection, "viewer_has_bookmarked", False)),
        },
    }


def collection_item_data(item: CollectionItem) -> dict:
    return {
        "id": item.id,
        "library_entry_id": item.user_subject_id,
        "entity": entity_summary(item.user_subject.entity, safe=True),
        "order": item.order,
        "relation": item.relation,
    }


@extend_schema_view(
    get=extend_schema(
        parameters=[CollectionListRequestSerializer, PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedCollection", UserCollectionSerializer)}
        ),
    ),
    post=extend_schema(
        request=CollectionCreateRequestSerializer,
        responses=api_responses({201: UserCollectionSerializer}),
    ),
)
class CollectionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CollectionListRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = CollectionSelector.list_my_collections(
            user=request.user, **serializer.validated_data
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [collection_data(item) for item in page]
        )

    def post(self, request):
        serializer = CollectionCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collection = CollectionService.create_collection(
            user=request.user, **serializer.validated_data
        )
        return Response(collection_data(collection), status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(responses=api_responses({200: UserCollectionSerializer})),
    patch=extend_schema(
        request=CollectionUpdateRequestSerializer,
        responses=api_responses({200: UserCollectionSerializer}),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class CollectionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, collection_id: int):
        collection = CollectionSelector.get_my_collection_or_raise(
            user=request.user, collection_id=collection_id
        )
        return Response(collection_data(collection))

    def patch(self, request, collection_id: int):
        serializer = CollectionUpdateRequestSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        collection = CollectionService.update_collection(
            user=request.user,
            collection_id=collection_id,
            **serializer.validated_data,
        )
        return Response(collection_data(collection))

    def delete(self, request, collection_id: int):
        CollectionService.delete_collection(
            user=request.user, collection_id=collection_id
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedCollectionItem", CollectionItemSerializer
                )
            }
        ),
    ),
    post=extend_schema(
        request=CollectionItemWriteSerializer,
        responses=api_responses(
            {200: CollectionItemSerializer, 201: CollectionItemSerializer}
        ),
    ),
    put=extend_schema(
        request=CollectionItemReplaceSerializer,
        responses=api_responses({200: CollectionItemSerializer(many=True)}),
    ),
)
class CollectionItemListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, collection_id: int):
        collection = CollectionSelector.get_my_collection_or_raise(
            user=request.user, collection_id=collection_id
        )
        queryset = CollectionSelector.list_collection_items(collection=collection)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [collection_item_data(item) for item in page]
        )

    def post(self, request, collection_id: int):
        serializer = CollectionItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        entry_id = values.pop("library_entry_id")
        item, created = CollectionService.add_collection_item(
            user=request.user,
            collection_id=collection_id,
            user_subject_id=entry_id,
            **values,
        )
        return Response(
            collection_item_data(item),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def put(self, request, collection_id: int):
        serializer = CollectionItemReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = [
            {
                "user_subject_id": item["library_entry_id"],
                "order": item["order"],
                "relation": item["relation"],
            }
            for item in serializer.validated_data["items"]
        ]
        queryset = CollectionService.replace_collection_items(
            user=request.user, collection_id=collection_id, items=items
        )
        return Response([collection_item_data(item) for item in queryset])


@extend_schema_view(
    patch=extend_schema(
        request=CollectionItemPatchSerializer,
        responses=api_responses({200: CollectionItemSerializer}),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class CollectionItemDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, collection_id: int, item_id: int):
        serializer = CollectionItemPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        queryset = CollectionService.update_collection_items(
            user=request.user,
            collection_id=collection_id,
            items=[{"id": item_id, **serializer.validated_data}],
        )
        item = next(item for item in queryset if item.id == item_id)
        return Response(collection_item_data(item))

    def delete(self, request, collection_id: int, item_id: int):
        CollectionService.delete_collection_item(
            user=request.user, collection_id=collection_id, item_id=item_id
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
