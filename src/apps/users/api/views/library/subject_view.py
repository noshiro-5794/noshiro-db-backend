from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.users.api.serializers.library.subject_serializer import (
    MySubjectContextResponseSerializer,
    UserSubjectCreateRequestSerializer,
    UserSubjectDetailResponseSerializer,
    UserSubjectListRequestSerializer,
    UserSubjectListResponseSerializer,
    UserSubjectUpdateRequestSerializer,
)
from apps.users.selectors.library.subject_selector import SubjectSelector
from apps.users.services.library.subject_service import UserSubjectService
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class MyUserSubjectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = UserSubjectListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = SubjectSelector.list_my_subjects(
            user=request.user,
            **query_serializer.validated_data,
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
