from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.api.serializers.contracts import UpdatedCountSerializer
from apps.community.api.serializers.notifications import (
    NotificationListRequestSerializer,
    NotificationResponseSerializer,
    NotificationUnreadCountResponseSerializer,
)
from apps.community.selectors.notification_selector import NotificationSelector
from apps.community.services.notification_service import NotificationService
from shared.api.contracts import (
    CursorPaginationQuerySerializer,
    api_responses,
    cursor_paginated_response,
)
from shared.api.pagination import TimelineCursorPagination


@extend_schema_view(
    get=extend_schema(
        parameters=[
            NotificationListRequestSerializer,
            CursorPaginationQuerySerializer,
        ],
        responses=api_responses(
            {
                200: cursor_paginated_response(
                    "CursorPaginatedNotification", NotificationResponseSerializer
                )
            }
        ),
    )
)
class MyNotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = NotificationListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = NotificationSelector.list_my_notifications(
            user=request.user,
            is_read=query_serializer.validated_data.get("is_read"),
        )

        paginator = TimelineCursorPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = NotificationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        responses=api_responses({200: NotificationUnreadCountResponseSerializer})
    )
)
class MyNotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = NotificationUnreadCountResponseSerializer(
            {"unread_count": NotificationSelector.unread_count(user=request.user)}
        )

        return Response(serializer.data)


@extend_schema_view(
    put=extend_schema(
        request=None,
        responses=api_responses({200: NotificationResponseSerializer}),
    )
)
class MyNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, notification_id: int):
        notification = NotificationSelector.get_my_notification_or_raise(
            user=request.user,
            notification_id=notification_id,
        )
        notification = NotificationService.mark_read(notification=notification)
        serializer = NotificationResponseSerializer(notification)

        return Response(serializer.data)


@extend_schema_view(
    put=extend_schema(
        request=None,
        responses=api_responses({200: UpdatedCountSerializer}),
    )
)
class MyNotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        updated_count = NotificationService.mark_all_read(user=request.user)

        return Response({"updated_count": updated_count})
