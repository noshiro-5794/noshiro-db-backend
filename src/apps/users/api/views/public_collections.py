from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.api.serializers.collections import CollectionListRequestSerializer
from apps.users.api.serializers.contracts import (
    CollectionItemSerializer,
    UserCollectionSerializer,
)
from apps.users.api.views.collections import (
    collection_data,
    collection_item_data,
)
from apps.users.api.views.profiles import get_public_user
from apps.users.selectors.public.public_profile_selector import PublicProfileSelector
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        parameters=[CollectionListRequestSerializer, PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedPublicCollection", UserCollectionSerializer
                )
            },
            errors=(404,),
        ),
    ),
)
class PublicCollectionListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = get_public_user(user_id=user_id, viewer=request.user)
        serializer = CollectionListRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = PublicProfileSelector.list_public_collections(
            user=user,
            viewer=request.user,
            **serializer.validated_data,
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [collection_data(item) for item in page]
        )


@extend_schema_view(
    get=extend_schema(
        responses=api_responses({200: UserCollectionSerializer}, errors=(404,))
    ),
)
class PublicCollectionDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int, collection_id: int):
        user = get_public_user(user_id=user_id, viewer=request.user)
        collection = PublicProfileSelector.get_public_collection(
            user=user,
            collection_id=collection_id,
            viewer=request.user,
        )
        if collection is None:
            raise NotFound("Collection not found.")
        return Response(collection_data(collection))


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedPublicCollectionItem", CollectionItemSerializer
                )
            },
            errors=(404,),
        ),
    ),
)
class PublicCollectionItemListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int, collection_id: int):
        user = get_public_user(user_id=user_id, viewer=request.user)
        collection = PublicProfileSelector.get_public_collection(
            user=user,
            collection_id=collection_id,
            viewer=request.user,
        )
        if collection is None:
            raise NotFound("Collection not found.")
        queryset = PublicProfileSelector.list_public_collection_items(
            collection=collection,
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            [collection_item_data(item) for item in page]
        )
