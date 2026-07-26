from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.api.serializers.comment_serializer import (
    CommunityCommentCreateRequestSerializer,
    CommunityCommentResponseSerializer,
)
from apps.community.api.serializers.post_serializer import (
    CommunityPostCreateRequestSerializer,
    CommunityPostListRequestSerializer,
    CommunityPostModerationRequestSerializer,
    CommunityPostResponseSerializer,
    CommunityPostUpdateRequestSerializer,
)
from apps.community.selectors.comment_selector import CommunityCommentSelector
from apps.community.selectors.post_selector import CommunityPostSelector
from apps.community.services.comment_service import CommunityCommentService
from apps.community.services.moderation_service import CommunityModerationService
from apps.community.services.post_service import CommunityPostService
from apps.index.selectors.subject_selector import SubjectSelector
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class CommunityPostListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request):
        query_serializer = CommunityPostListRequestSerializer(
            data=request.query_params,
        )
        query_serializer.is_valid(raise_exception=True)

        qs = CommunityPostSelector.list_public_posts(
            viewer=request.user,
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CommunityPostResponseSerializer(
            page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = CommunityPostCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subject = None
        subject_id = serializer.validated_data.pop("subject_id", None)
        if subject_id:
            subject = SubjectSelector.get_subject_or_raise(subject_id=subject_id)

        post = CommunityPostService.create_post(
            author=request.user,
            subject=subject,
            **serializer.validated_data,
        )
        output_serializer = CommunityPostResponseSerializer(
            post,
            context={"request": request},
        )

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED,
        )


class CommunityPostDetailView(APIView):
    def get_permissions(self):
        if self.request.method in {"PATCH", "DELETE"}:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, post_id: int):
        post = CommunityPostSelector.get_public_post_or_raise(
            post_id=post_id,
            viewer=request.user,
        )
        serializer = CommunityPostResponseSerializer(
            post,
            context={"request": request},
        )

        return success_response(data=serializer.data)

    def patch(self, request, post_id: int):
        serializer = CommunityPostUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        post = CommunityPostService.update_post(
            author=request.user,
            post_id=post_id,
            **serializer.validated_data,
        )
        output_serializer = CommunityPostResponseSerializer(
            post,
            context={"request": request},
        )

        return success_response(data=output_serializer.data)

    def delete(self, request, post_id: int):
        CommunityPostService.delete_post(
            author=request.user,
            post_id=post_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffCommunityPostModerationView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, post_id: int):
        serializer = CommunityPostModerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        post = CommunityModerationService.moderate_post(
            moderator=request.user,
            post_id=post_id,
            **serializer.validated_data,
        )

        output_serializer = CommunityPostResponseSerializer(
            post,
            context={"request": request},
        )
        return success_response(data=output_serializer.data)


class CommunityPostCommentListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def get(self, request, post_id: int):
        post = CommunityPostSelector.get_public_post_or_raise(
            post_id=post_id,
            viewer=request.user,
        )
        qs = CommunityCommentSelector.list_public_post_comments(
            post=post,
            viewer=request.user,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CommunityCommentResponseSerializer(
            page,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data)

    def post(self, request, post_id: int):
        post = CommunityPostSelector.get_public_post_or_raise(
            post_id=post_id,
            viewer=request.user,
        )
        serializer = CommunityCommentCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comment = CommunityCommentService.create_post_comment(
            author=request.user,
            post=post,
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
