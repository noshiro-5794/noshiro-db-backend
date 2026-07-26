from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.community.api.serializers.notification_serializer import (
    NotificationListRequestSerializer,
    NotificationResponseSerializer,
    NotificationUnreadCountResponseSerializer,
)
from apps.community.selectors.notification_selector import NotificationSelector
from apps.community.services.notification_service import NotificationService
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class MyNotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = NotificationListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = NotificationSelector.list_my_notifications(
            user=request.user,
            is_read=query_serializer.validated_data.get("is_read"),
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = NotificationResponseSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)


class MyNotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = NotificationUnreadCountResponseSerializer(
            {"unread_count": NotificationSelector.unread_count(user=request.user)}
        )

        return success_response(data=serializer.data)


class MyNotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id: int):
        notification = NotificationSelector.get_my_notification_or_raise(
            user=request.user,
            notification_id=notification_id,
        )
        notification = NotificationService.mark_read(notification=notification)
        serializer = NotificationResponseSerializer(notification)

        return success_response(data=serializer.data)


class MyNotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated_count = NotificationService.mark_all_read(user=request.user)

        return success_response(data={"updated_count": updated_count})
