from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.activity_serializer import (
    ActivityListRequestSerializer,
    ActivityResponseSerializer,
    FeedListRequestSerializer,
)
from apps.community.selectors.activity_selector import ActivitySelector
from apps.users.selectors.public.public_profile_selector import PublicProfileSelector
from shared.api.pagination import DefaultPageNumberPagination


class PublicActivityListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query_serializer = ActivityListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ActivitySelector.list_public_activities(
            viewer=request.user,
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MyActivityListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = ActivityListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ActivitySelector.list_my_activities(
            user=request.user,
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


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

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MyFeedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = FeedListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = ActivitySelector.list_my_feed(
            user=request.user,
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)
