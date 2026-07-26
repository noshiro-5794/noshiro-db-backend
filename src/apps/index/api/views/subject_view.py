from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.index.api.serializers.subject_serializer import (
    SubjectDetailResponseSerializer,
    SubjectListQuerySerializer,
    SubjectListResponseSerializer,
)
from apps.index.selectors.subject_selector import SubjectSelector
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class SubjectListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query_serializer = SubjectListQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = SubjectSelector.list_subjects(
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        serializer = SubjectListResponseSerializer(
            page,
            many=True,
        )

        return paginator.get_paginated_response(serializer.data)


class SubjectDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, subject_id):
        subject = SubjectSelector.get_subject_or_raise(subject_id=subject_id)

        serializer = SubjectDetailResponseSerializer(subject)

        return success_response(data=serializer.data)
