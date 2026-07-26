from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.interaction_serializer import (
    CommunityBookmarkListRequestSerializer,
    CommunityBookmarkRequestSerializer,
    CommunityBookmarkResponseSerializer,
    CommunityReactionDeleteRequestSerializer,
    CommunityReactionRequestSerializer,
    CommunityReactionResponseSerializer,
)
from apps.community.selectors.interaction_selector import CommunityBookmarkSelector
from apps.community.services.interaction_service import CommunityInteractionService
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


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
        query_serializer = CommunityBookmarkListRequestSerializer(
            data=request.query_params,
        )
        query_serializer.is_valid(raise_exception=True)

        qs = CommunityBookmarkSelector.list_my_bookmarks(
            user=request.user,
            **query_serializer.validated_data,
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
