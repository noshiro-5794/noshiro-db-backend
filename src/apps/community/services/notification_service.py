from django.utils import timezone

from apps.community.models import Notification


class NotificationService:
    @staticmethod
    def _create_notification(
        *,
        recipient,
        actor,
        notification_type,
        activity=None,
        post=None,
        comment=None,
        review=None,
        collection=None,
        metadata=None,
    ):
        if not recipient or not actor or recipient.id == actor.id:
            return None

        return Notification.objects.create(
            recipient=recipient,
            actor=actor,
            notification_type=notification_type,
            activity=activity,
            post=post,
            comment=comment,
            review=review,
            collection=collection,
            metadata=metadata or {},
        )

    @classmethod
    def create_followed_notification(cls, *, recipient, actor, activity=None):
        return cls._create_notification(
            recipient=recipient,
            actor=actor,
            notification_type=Notification.NotificationType.FOLLOWED,
            activity=activity,
            metadata={"actor_id": actor.id},
        )

    @classmethod
    def create_commented_notification(
        cls,
        *,
        recipient,
        actor,
        activity=None,
        post=None,
        comment=None,
        review=None,
        collection=None,
    ):
        return cls._create_notification(
            recipient=recipient,
            actor=actor,
            notification_type=Notification.NotificationType.COMMENTED,
            activity=activity,
            post=post,
            comment=comment,
            review=review,
            collection=collection,
            metadata={
                "post_id": post.id if post else None,
                "comment_id": comment.id if comment else None,
                "review_id": review.id if review else None,
                "collection_id": collection.id if collection else None,
            },
        )

    @classmethod
    def create_reacted_notification(
        cls,
        *,
        recipient,
        actor,
        post=None,
        comment=None,
        review=None,
        collection=None,
        activity=None,
        reaction_type="like",
    ):
        return cls._create_notification(
            recipient=recipient,
            actor=actor,
            notification_type=Notification.NotificationType.REACTED,
            activity=activity,
            post=post,
            comment=comment,
            review=review,
            collection=collection,
            metadata={"reaction_type": reaction_type},
        )

    @staticmethod
    def mark_read(*, notification):
        if notification.read_at:
            return notification

        read_at = timezone.now()
        updated = Notification.objects.filter(
            pk=notification.pk,
            read_at__isnull=True,
        ).update(read_at=read_at)
        if updated:
            notification.read_at = read_at
        else:
            notification.refresh_from_db(fields=["read_at"])
        return notification

    @staticmethod
    def mark_all_read(*, user):
        return Notification.objects.filter(
            recipient=user,
            read_at__isnull=True,
        ).update(read_at=timezone.now())
