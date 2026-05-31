from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.core.response import success_response
from apps.core.pagination import DefaultPageNumberPagination
from apps.users.selectors.subject_selector import SubjectSelector
from apps.users.services.library.subject_service import UserSubjectService
from apps.users.api.serializers.subject_serializer import (
    UserSubjectCreateRequestSerializer,
    UserSubjectDetailResponseSerializer,
    UserSubjectListResponseSerializer,
    UserSubjectUpdateRequestSerializer,
    MySubjectContextResponseSerializer,
)


class MyUserSubjectListCreateView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SubjectSelector.list_my_subjects(
            user=request.user,
            status=request.query_params.get("status"),
            subject_type=request.query_params.get("subject_type"),
            keyword=request.query_params.get("keyword"),
            tag_id=request.query_params.get("tag_id"),
            ordering=request.query_params.get("ordering", "-updated_at"),
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = UserSubjectListResponseSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = UserSubjectCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_subject, created = UserSubjectService.add_subject(
            user=request.user, **serializer.validated_data
        )
        output_serializer = UserSubjectDetailResponseSerializer(user_subject)
        return success_response(
            data=output_serializer.data,
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MyUserSubjectDetailView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, user_subject_id: int):
        user_subject = SubjectSelector.get_user_subject_or_raise(
            user=request.user, user_subject_id=user_subject_id
        )
        serializer = UserSubjectDetailResponseSerializer(user_subject)
        return success_response(data=serializer.data)

    def patch(self, request, user_subject_id: int):
        serializer = UserSubjectUpdateRequestSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user_subject = UserSubjectService.update_subject(
            user=request.user,
            user_subject_id=user_subject_id,
            **serializer.validated_data,
        )
        output_serializer = UserSubjectDetailResponseSerializer(user_subject)
        return success_response(data=output_serializer.data)

    def delete(self, request, user_subject_id: int):
        UserSubjectService.delete_subject(
            user=request.user, user_subject_id=user_subject_id
        )
        return success_response(data=None, status_code=status.HTTP_204_NO_CONTENT)


class MySubjectContextView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, subject_id):
        data = SubjectSelector.get_my_subject_context(
            user=request.user,
            subject_id=subject_id,
        )
        serializer = MySubjectContextResponseSerializer(data)
        return success_response(data=serializer.data)
