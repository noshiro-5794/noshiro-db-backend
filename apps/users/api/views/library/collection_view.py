from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.core.response import success_response
from apps.core.pagination import DefaultPageNumberPagination
from apps.users.selectors.library.collection_selector import CollectionSelector
from apps.users.services.library.collection_service import CollectionService
from apps.users.api.serializers.library.collection_serializer import (
    CollectionCreateRequestSerializer,
    CollectionUpdateRequestSerializer,
    CollectionItemCreateRequestSerializer,
    CollectionItemReplaceRequestSerializer,
    CollectionItemUpdateRequestSerializer,
    CollectionListResponseSerializer,
    CollectionDetailResponseSerializer,
    CollectionItemResponseSerializer,
)


class MyCollectionListCreateView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = CollectionSelector.list_my_collections(
            user=request.user,
            keyword=request.query_params.get("keyword"),
            ordering=request.query_params.get("ordering", "id"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = CollectionListResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = CollectionCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        collection = CollectionService.create_collection(
            user=request.user,
            **serializer.validated_data,
        )

        output_serializer = CollectionDetailResponseSerializer(collection)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class MyCollectionDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, collection_id: int):
        collection = CollectionSelector.get_my_collection_or_raise(
            user=request.user,
            collection_id=collection_id,
        )

        serializer = CollectionDetailResponseSerializer(collection)

        return success_response(data=serializer.data)

    def patch(self, request, collection_id: int):
        serializer = CollectionUpdateRequestSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        collection = CollectionService.update_collection(
            user=request.user,
            collection_id=collection_id,
            **serializer.validated_data,
        )

        output_serializer = CollectionDetailResponseSerializer(collection)

        return success_response(data=output_serializer.data)

    def delete(self, request, collection_id: int):
        CollectionService.delete_collection(
            user=request.user,
            collection_id=collection_id,
        )

        return success_response(
            data=None,
            status_code=status.HTTP_204_NO_CONTENT,
        )


class MyCollectionItemListCreateReplaceView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, collection_id: int):
        collection = CollectionSelector.get_my_collection_or_raise(
            user=request.user,
            collection_id=collection_id,
        )

        qs = CollectionSelector.list_collection_items(
            collection=collection,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = CollectionItemResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)

    def post(self, request, collection_id: int):
        serializer = CollectionItemCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item, created = CollectionService.add_collection_item(
            user=request.user,
            collection_id=collection_id,
            **serializer.validated_data,
        )

        output_serializer = CollectionItemResponseSerializer(item)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def put(self, request, collection_id: int):
        serializer = CollectionItemReplaceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        qs = CollectionService.replace_collection_items(
            user=request.user,
            collection_id=collection_id,
            items=serializer.validated_data["items"],
        )

        output_serializer = CollectionItemResponseSerializer(
            qs,
            many=True,
        )

        return success_response(data=output_serializer.data)

    def patch(self, request, collection_id: int):
        serializer = CollectionItemUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        qs = CollectionService.update_collection_items(
            user=request.user,
            collection_id=collection_id,
            items=serializer.validated_data["items"],
        )

        output_serializer = CollectionItemResponseSerializer(
            qs,
            many=True,
        )

        return success_response(data=output_serializer.data)


class MyCollectionItemDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, collection_id: int, item_id: int):
        CollectionService.delete_collection_item(
            user=request.user,
            collection_id=collection_id,
            item_id=item_id,
        )

        return success_response(
            data=None,
            status_code=status.HTTP_204_NO_CONTENT,
        )
