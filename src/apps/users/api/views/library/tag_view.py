from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.users.api.serializers.library.tag_serializer import (
    UserSubjectTagReplaceRequestSerializer,
    UserTagCreateRequestSerializer,
    UserTagResponseSerializer,
    UserTagUpdateRequestSerializer,
)
from apps.users.selectors.library.tag_selector import UserTagSelector
from apps.users.services.library.tag_service import UserTagService
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class MyUserTagListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = UserTagSelector.list_my_tags(
            user=request.user,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = UserTagResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = UserTagCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tag, created = UserTagService.create_tag(
            user=request.user,
            name=serializer.validated_data["name"],
        )

        output_serializer = UserTagResponseSerializer(tag)

        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MyUserTagDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, tag_id: int):
        serializer = UserTagUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tag = UserTagService.update_tag(
            user=request.user,
            tag_id=tag_id,
            name=serializer.validated_data["name"],
        )

        output_serializer = UserTagResponseSerializer(tag)

        return success_response(data=output_serializer.data)

    def delete(self, request, tag_id: int):
        UserTagService.delete_tag(
            user=request.user,
            tag_id=tag_id,
        )

        return success_response(
            data=None,
            status_code=status.HTTP_204_NO_CONTENT,
        )


class MyUserSubjectTagView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_subject_id: int):
        qs = UserTagSelector.list_subject_tags(
            user=request.user,
            user_subject_id=user_subject_id,
        )

        serializer = UserTagResponseSerializer(qs, many=True)

        return success_response(data=serializer.data)

    def put(self, request, user_subject_id: int):
        serializer = UserSubjectTagReplaceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        qs = UserTagService.replace_subject_tags(
            user=request.user,
            user_subject_id=user_subject_id,
            tag_ids=serializer.validated_data.get("tag_ids"),
            tag_names=serializer.validated_data.get("tag_names"),
        )

        output_serializer = UserTagResponseSerializer(qs, many=True)

        return success_response(data=output_serializer.data)


class MySubjectTagView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, subject_id):
        qs = UserTagSelector.list_subject_tags_by_subject_id(
            user=request.user,
            subject_id=subject_id,
        )

        serializer = UserTagResponseSerializer(qs, many=True)

        return success_response(data=serializer.data)

    def put(self, request, subject_id):
        serializer = UserSubjectTagReplaceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        qs = UserTagService.replace_subject_tags_by_subject_id(
            user=request.user,
            subject_id=subject_id,
            tag_ids=serializer.validated_data.get("tag_ids"),
            tag_names=serializer.validated_data.get("tag_names"),
        )

        output_serializer = UserTagResponseSerializer(qs, many=True)

        return success_response(data=output_serializer.data)
