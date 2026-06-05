from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.interaction_serializer import (
    CommunityBookmarkRequestSerializer,
    CommunityBookmarkResponseSerializer,
    CommunityReactionDeleteRequestSerializer,
    CommunityReactionRequestSerializer,
    CommunityReactionResponseSerializer,
)
from apps.community.exceptions import CommunityTargetInvalid
from apps.community.selectors.interaction_selector import CommunityBookmarkSelector
from apps.community.selectors.target_selector import CommunityTargetSelector
from apps.community.services.interaction_service import CommunityInteractionService
from apps.core.pagination import DefaultPageNumberPagination
from apps.core.response import success_response


class CommunityReactionToggleView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CommunityReactionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reaction, created = CommunityInteractionService.react(
            user=request.user,
            **serializer.validated_data,
        )
        output_serializer = CommunityReactionResponseSerializer(reaction)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request):
        serializer = CommunityReactionDeleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        CommunityInteractionService.unreact(
            user=request.user,
            **serializer.validated_data,
        )

        return success_response(data=None, status_code=status.HTTP_204_NO_CONTENT)


class CommunityBookmarkListToggleView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        target_type = request.query_params.get("target_type")
        if target_type and target_type not in CommunityTargetSelector.BOOKMARK_TARGETS:
            raise CommunityTargetInvalid()

        qs = CommunityBookmarkSelector.list_my_bookmarks(
            user=request.user,
            target_type=target_type,
            keyword=request.query_params.get("keyword"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CommunityBookmarkResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = CommunityBookmarkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bookmark, created = CommunityInteractionService.bookmark(
            user=request.user,
            **serializer.validated_data,
        )
        output_serializer = CommunityBookmarkResponseSerializer(bookmark)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request):
        serializer = CommunityBookmarkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        CommunityInteractionService.unbookmark(
            user=request.user,
            **serializer.validated_data,
        )

        return success_response(data=None, status_code=status.HTTP_204_NO_CONTENT)
