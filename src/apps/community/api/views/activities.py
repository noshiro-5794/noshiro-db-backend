from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.activities import (
    ActivityListRequestSerializer,
    ActivityResponseSerializer,
    FeedListRequestSerializer,
)
from apps.community.selectors.activity_selector import ActivitySelector
from apps.users.selectors.public.public_profile_selector import PublicProfileSelector
from shared.api.contracts import (
    CursorPaginationQuerySerializer,
    api_responses,
    cursor_paginated_response,
)
from shared.api.pagination import TimelineCursorPagination


@extend_schema_view(
    get=extend_schema(
        parameters=[ActivityListRequestSerializer, CursorPaginationQuerySerializer],
        responses=api_responses(
            {
                200: cursor_paginated_response(
                    "CursorPaginatedActivity", ActivityResponseSerializer
                )
            },
            errors=(400,),
        ),
    )
)
class PublicActivityListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query_serializer = ActivityListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ActivitySelector.list_public_activities(
            viewer=request.user,
            **query_serializer.validated_data,
        )

        paginator = TimelineCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[ActivityListRequestSerializer, CursorPaginationQuerySerializer],
        responses=api_responses(
            {
                200: cursor_paginated_response(
                    "CursorPaginatedActivity", ActivityResponseSerializer
                )
            }
        ),
    )
)
class MyActivityListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = ActivityListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ActivitySelector.list_my_activities(
            user=request.user,
            **query_serializer.validated_data,
        )

        paginator = TimelineCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[ActivityListRequestSerializer, CursorPaginationQuerySerializer],
        responses=api_responses(
            {
                200: cursor_paginated_response(
                    "CursorPaginatedActivity", ActivityResponseSerializer
                )
            },
            errors=(400, 404),
        ),
    )
)
class PublicUserActivityListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = PublicProfileSelector.get_user_by_id_or_raise(
            user_id=user_id,
            viewer=request.user,
        )
        query_serializer = ActivityListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ActivitySelector.list_public_user_activities(
            user=user,
            viewer=request.user,
            **query_serializer.validated_data,
        )

        paginator = TimelineCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[FeedListRequestSerializer, CursorPaginationQuerySerializer],
        responses=api_responses(
            {
                200: cursor_paginated_response(
                    "CursorPaginatedActivity", ActivityResponseSerializer
                )
            }
        ),
    )
)
class MyFeedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = FeedListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ActivitySelector.list_my_feed(
            user=request.user,
            **query_serializer.validated_data,
        )

        paginator = TimelineCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)
