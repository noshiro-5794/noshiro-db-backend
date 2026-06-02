from apps.community.exceptions import NotificationNotFound
from apps.community.models import Notification


class NotificationSelector:

    @staticmethod
    def base_queryset():
        return Notification.objects.select_related(
            "actor",
            "actor__profile",
            "activity",
            "post",
            "comment",
            "review",
            "collection",
        )

    @classmethod
    def list_my_notifications(cls, *, user, is_read=None):
        qs = cls.base_queryset().filter(recipient=user)

        if is_read is True:
            qs = qs.filter(read_at__isnull=False)
        elif is_read is False:
            qs = qs.filter(read_at__isnull=True)

        return qs.order_by("-created_at", "-id")

    @staticmethod
    def unread_count(*, user):
        return Notification.objects.filter(
            recipient=user,
            read_at__isnull=True,
        ).count()

    @classmethod
    def get_my_notification_or_raise(cls, *, user, notification_id: int):
        notification = cls.base_queryset().filter(
            recipient=user,
            id=notification_id,
        ).first()

        if not notification:
            raise NotificationNotFound()

        return notification
