from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.api.serializers.comment_serializer import (
    CommunityCommentModerationRequestSerializer,
    CommunityCommentResponseSerializer,
    CommunityCommentUpdateRequestSerializer,
    CommunityTargetCommentCreateRequestSerializer,
    CommunityTargetCommentListRequestSerializer,
)
from apps.community.selectors.comment_selector import CommunityCommentSelector
from apps.community.services.comment_service import CommunityCommentService
from apps.community.services.moderation_service import CommunityModerationService
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class CommunityCommentListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        query_serializer = CommunityTargetCommentListRequestSerializer(
            data=request.query_params,
        )
        query_serializer.is_valid(raise_exception=True)

        qs = CommunityCommentSelector.list_public_comments(
            viewer=request.user,
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CommunityCommentResponseSerializer(
            page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = CommunityTargetCommentCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = CommunityCommentService.create_comment(
            author=request.user,
            **serializer.validated_data,
        )
        output_serializer = CommunityCommentResponseSerializer(
            comment,
            context={"request": request},
        )

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class CommunityCommentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, comment_id: int):
        serializer = CommunityCommentUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = CommunityCommentService.update_comment(
            author=request.user,
            comment_id=comment_id,
            **serializer.validated_data,
        )
        output_serializer = CommunityCommentResponseSerializer(
            comment,
            context={"request": request},
        )

        return success_response(data=output_serializer.data)

    def delete(self, request, comment_id: int):
        CommunityCommentService.delete_comment(
            author=request.user,
            comment_id=comment_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffCommunityCommentModerationView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, comment_id: int):
        serializer = CommunityCommentModerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = CommunityModerationService.moderate_comment(
            moderator=request.user,
            comment_id=comment_id,
            **serializer.validated_data,
        )

        output_serializer = CommunityCommentResponseSerializer(
            comment,
            context={"request": request},
        )
        return success_response(data=output_serializer.data)
