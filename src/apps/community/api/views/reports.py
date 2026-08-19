from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.api.serializers.reports import (
    CommunityReportCreateRequestSerializer,
    CommunityReportListRequestSerializer,
    CommunityReportResolveRequestSerializer,
    CommunityReportResponseSerializer,
)
from apps.community.selectors.report_selector import CommunityReportSelector
from apps.community.services.report_service import CommunityReportService
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


@extend_schema_view(
    post=extend_schema(
        request=CommunityReportCreateRequestSerializer,
        responses=api_responses({201: CommunityReportResponseSerializer}),
    )
)
class CommunityReportCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CommunityReportCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = CommunityReportService.create_report(
            reporter=request.user,
            **serializer.validated_data,
        )
        output_serializer = CommunityReportResponseSerializer(report)

        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedCommunityReport", CommunityReportResponseSerializer
                )
            }
        ),
    )
)
class MyCommunityReportListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = CommunityReportSelector.list_my_reports(user=request.user)

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CommunityReportResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        parameters=[CommunityReportListRequestSerializer, PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedCommunityReport", CommunityReportResponseSerializer
                )
            }
        ),
    )
)
class StaffCommunityReportListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        query_serializer = CommunityReportListRequestSerializer(
            data=request.query_params
        )
        query_serializer.is_valid(raise_exception=True)

        qs = CommunityReportSelector.list_reports_for_staff(
            status=query_serializer.validated_data.get("status"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = CommunityReportResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    patch=extend_schema(
        request=CommunityReportResolveRequestSerializer,
        responses=api_responses({200: CommunityReportResponseSerializer}),
    )
)
class StaffCommunityReportResolveView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, report_id: int):
        report = CommunityReportSelector.get_report_for_staff_or_raise(
            report_id=report_id,
        )
        serializer = CommunityReportResolveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = CommunityReportService.resolve_report(
            report=report,
            moderator=request.user,
            **serializer.validated_data,
        )
        output_serializer = CommunityReportResponseSerializer(report)

        return Response(output_serializer.data)
