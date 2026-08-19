from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.relationships import (
    UserBlockResponseSerializer,
    UserMuteResponseSerializer,
)
from apps.community.selectors.relationship_selector import UserRelationshipSelector
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedUserBlock", UserBlockResponseSerializer)}
        ),
    )
)
class MyBlockListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserRelationshipSelector.list_block_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = UserBlockResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedUserMute", UserMuteResponseSerializer)}
        ),
    )
)
class MyMuteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserRelationshipSelector.list_mute_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = UserMuteResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)
