from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from apps.core.response import success_response
from apps.core.pagination import DefaultPageNumberPagination
from apps.users.selectors.public.public_profile_selector import PublicProfileSelector
from apps.users.api.serializers.public.public_profile_serializer import (
    PublicUserProfileResponseSerializer,
    PublicUserSubjectResponseSerializer,
    PublicReviewResponseSerializer,
    PublicCollectionResponseSerializer,
)


class PublicUserProfileView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = PublicProfileSelector.get_public_profile(
            target_user_id=user_id,
            viewer=request.user,
        )

        serializer = PublicUserProfileResponseSerializer(
            user,
            context={
                "request": request,
            },
        )

        return success_response(data=serializer.data)


class PublicUserSubjectListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = PublicProfileSelector.get_user_by_id_or_raise(
            user_id=user_id,
        )

        qs = PublicProfileSelector.list_public_user_subjects(
            user=user,
            status=request.query_params.get("status"),
            subject_type=request.query_params.get("subject_type"),
            keyword=request.query_params.get("keyword"),
            ordering=request.query_params.get("ordering", "-id"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = PublicUserSubjectResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class PublicUserReviewListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = PublicProfileSelector.get_user_by_id_or_raise(
            user_id=user_id,
        )

        qs = PublicProfileSelector.list_public_reviews(
            user=user,
            keyword=request.query_params.get("keyword"),
            ordering=request.query_params.get("ordering", "-id"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = PublicReviewResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class PublicUserCollectionListView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = PublicProfileSelector.get_user_by_id_or_raise(
            user_id=user_id,
        )

        qs = PublicProfileSelector.list_public_collections(
            user=user,
            keyword=request.query_params.get("keyword"),
            ordering=request.query_params.get("ordering", "-id"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = PublicCollectionResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)
