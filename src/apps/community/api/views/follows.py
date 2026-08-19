from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.follows import (
    FollowerRelationResponseSerializer,
    FollowingRelationResponseSerializer,
)
from apps.community.selectors.follow_selector import UserFollowSelector
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
            {
                200: paginated_response(
                    "PaginatedFollowingRelation", FollowingRelationResponseSerializer
                )
            }
        ),
    )
)
class MyFollowingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserFollowSelector.list_following_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowingRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedFollowerRelation", FollowerRelationResponseSerializer
                )
            }
        ),
    )
)
class MyFollowerListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserFollowSelector.list_follower_relations(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowerRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedFollowingRelation", FollowingRelationResponseSerializer
                )
            },
            errors=(404,),
        ),
    )
)
class UserFollowingListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = UserFollowSelector.get_user_by_id_or_raise(user_id=user_id)
        qs = UserFollowSelector.list_following_relations(user=user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowingRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedFollowerRelation", FollowerRelationResponseSerializer
                )
            },
            errors=(404,),
        ),
    )
)
class UserFollowerListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = UserFollowSelector.get_user_by_id_or_raise(user_id=user_id)
        qs = UserFollowSelector.list_follower_relations(user=user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = FollowerRelationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)
