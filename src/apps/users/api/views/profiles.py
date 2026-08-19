from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.models import UserBlock, UserFollow
from apps.users.api.serializers.contracts import (
    LibraryEntrySerializer,
    PublicLibraryQuerySerializer,
    PublicUserSerializer,
    ReviewSerializer,
)
from apps.users.api.views.library import library_entry_data, library_entry_queryset
from apps.users.api.views.profile import (
    MyAvatarUploadView,
    MyProfileStatsView,
    MyProfileView,
    MySettingsView,
)
from apps.users.api.views.reviews import review_data, review_queryset
from apps.users.models import Collection, Review, UserSubject
from apps.users.models.account import User
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


def get_public_user(*, user_id: int, viewer):
    try:
        user = User.objects.select_related("profile").get(pk=user_id)
    except User.DoesNotExist as exc:
        raise NotFound("User not found.") from exc
    if (
        viewer.is_authenticated
        and UserBlock.objects.filter(
            Q(user=viewer, blocked_user=user) | Q(user=user, blocked_user=viewer)
        ).exists()
    ):
        raise NotFound("User not found.")
    return user


@extend_schema_view(
    get=extend_schema(
        responses=api_responses({200: PublicUserSerializer}, errors=(404,))
    )
)
class PublicUserDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = get_public_user(user_id=user_id, viewer=request.user)
        profile = getattr(user, "profile", None)
        stats = {
            "library_entry_count": UserSubject.objects.filter(
                user=user, entity__isnull=False, is_public=True
            ).count(),
            "review_count": Review.objects.filter(
                user_subject__user=user,
                user_subject__entity__isnull=False,
                user_subject__is_public=True,
                is_public=True,
            ).count(),
            "collection_count": Collection.objects.filter(
                user=user, is_public=True
            ).count(),
            "following_count": UserFollow.objects.filter(follower=user).count(),
            "follower_count": UserFollow.objects.filter(following=user).count(),
        }
        return Response(
            {
                "id": user.id,
                "nickname": profile.nickname if profile else "",
                "avatar": profile.avatar if profile else "",
                "bio": profile.bio if profile else "",
                "stats": stats,
                "is_following": bool(
                    request.user.is_authenticated
                    and UserFollow.objects.filter(
                        follower=request.user, following=user
                    ).exists()
                ),
            }
        )


@extend_schema_view(
    get=extend_schema(
        parameters=[PublicLibraryQuerySerializer, PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedLibraryEntry", LibraryEntrySerializer)},
            errors=(400, 404),
        ),
    )
)
class PublicUserLibraryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = get_public_user(user_id=user_id, viewer=request.user)
        serializer = PublicLibraryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = library_entry_queryset(user=user).filter(is_public=True)
        if entry_status := serializer.validated_data.get("status"):
            queryset = queryset.filter(status=entry_status)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(
            queryset.order_by("-updated_at", "-id"), request, view=self
        )
        return paginator.get_paginated_response(
            [library_entry_data(entry) for entry in page]
        )


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter("query", OpenApiTypes.STR),
            PaginationQuerySerializer,
        ],
        responses=api_responses(
            {200: paginated_response("PaginatedReview", ReviewSerializer)},
            errors=(400, 404),
        ),
    )
)
class PublicUserReviewListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id: int):
        user = get_public_user(user_id=user_id, viewer=request.user)
        queryset = review_queryset(viewer=request.user).filter(
            user_subject__user=user,
            user_subject__entity__isnull=False,
            user_subject__is_public=True,
            is_public=True,
        )
        if keyword := request.query_params.get("query", "").strip():
            queryset = queryset.filter(
                Q(title__icontains=keyword) | Q(content__icontains=keyword)
            )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(
            queryset.order_by("-created_at", "-id"), request, view=self
        )
        return paginator.get_paginated_response([review_data(item) for item in page])


__all__ = [
    "MyAvatarUploadView",
    "MyProfileStatsView",
    "MyProfileView",
    "MySettingsView",
    "PublicUserDetailView",
    "PublicUserLibraryView",
    "PublicUserReviewListView",
]
