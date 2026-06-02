from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.activity_serializer import ActivityResponseSerializer
from apps.community.selectors.activity_selector import ActivitySelector
from apps.core.pagination import DefaultPageNumberPagination
from apps.users.selectors.public.public_profile_selector import PublicProfileSelector


class MyActivityListView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ActivitySelector.list_my_activities(
            user=request.user,
            activity_type=request.query_params.get("activity_type"),
            ordering=request.query_params.get("ordering", "-created_at"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class PublicUserActivityListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = PublicProfileSelector.get_user_by_id_or_raise(user_id=user_id)

        qs = ActivitySelector.list_public_user_activities(
            user=user,
            activity_type=request.query_params.get("activity_type"),
            ordering=request.query_params.get("ordering", "-created_at"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MyFeedView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        include_self = str(request.query_params.get("include_self")).lower() in {
            "1",
            "true",
            "yes",
        }

        qs = ActivitySelector.list_my_feed(
            user=request.user,
            activity_type=request.query_params.get("activity_type"),
            include_self=include_self,
            ordering=request.query_params.get("ordering", "-created_at"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ActivityResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)
