from django.db.models import Q, Subquery

from apps.community.models import (
    Activity,
    FeedPolicy,
    UserBlock,
    UserFollow,
    UserMute,
    Visibility,
)


class ActivitySelector:

    @staticmethod
    def base_queryset():
        return Activity.objects.select_related(
            "user",
            "user__profile",
            "target_user",
            "target_user__profile",
            "subject",
            "user_subject",
            "user_subject__subject",
            "review",
            "review__user_subject",
            "review__user_subject__subject",
            "collection",
            "collection_item",
            "collection_item__collection",
            "collection_item__user_subject",
            "collection_item__user_subject__subject",
            "post",
            "post__subject",
            "comment",
        )

    @staticmethod
    def public_visibility_filter():
        return (
            Q(visibility=Visibility.PUBLIC)
            & ~Q(feed_policy=FeedPolicy.HIDDEN)
            & (Q(user_subject__isnull=True) | Q(user_subject__is_public=True))
            & (
                Q(review__isnull=True)
                | (
                    Q(review__is_public=True)
                    & Q(review__user_subject__is_public=True)
                )
            )
            & (Q(collection__isnull=True) | Q(collection__is_public=True))
            & (
                Q(collection_item__isnull=True)
                | (
                    Q(collection_item__collection__is_public=True)
                    & Q(collection_item__user_subject__is_public=True)
                )
            )
        )

    @classmethod
    def list_my_activities(
        cls,
        *,
        user,
        activity_type=None,
        ordering="-created_at",
    ):
        qs = cls.base_queryset().filter(user=user)

        if activity_type:
            qs = qs.filter(activity_type=activity_type)

        allowed_ordering = {
            "created_at",
            "-created_at",
            "id",
            "-id",
        }

        if ordering not in allowed_ordering:
            ordering = "-created_at"

        return qs.order_by(ordering, "-id")

    @classmethod
    def list_public_user_activities(
        cls,
        *,
        user,
        activity_type=None,
        ordering="-created_at",
    ):
        qs = (
            cls.base_queryset()
            .filter(user=user)
            .filter(cls.public_visibility_filter())
        )

        if activity_type:
            qs = qs.filter(activity_type=activity_type)

        allowed_ordering = {
            "created_at",
            "-created_at",
            "id",
            "-id",
        }

        if ordering not in allowed_ordering:
            ordering = "-created_at"

        return qs.order_by(ordering, "-id")

    @classmethod
    def list_my_feed(
        cls,
        *,
        user,
        activity_type=None,
        include_self=False,
        ordering="-created_at",
    ):
        following_user_ids = UserFollow.objects.filter(
            follower=user,
        ).values("following_id")
        blocked_user_ids = UserBlock.objects.filter(
            user=user,
        ).values("blocked_user_id")
        blocking_user_ids = UserBlock.objects.filter(
            blocked_user=user,
        ).values("user_id")
        muted_user_ids = UserMute.objects.filter(
            user=user,
        ).values("muted_user_id")

        qs = (
            cls.base_queryset()
            .filter(user_id__in=Subquery(following_user_ids))
            .exclude(user_id__in=Subquery(blocked_user_ids))
            .exclude(user_id__in=Subquery(blocking_user_ids))
            .exclude(user_id__in=Subquery(muted_user_ids))
            .filter(cls.public_visibility_filter())
        )

        if include_self:
            qs = qs | (
                cls.base_queryset()
                .filter(user=user)
                .filter(cls.public_visibility_filter())
            )

        if activity_type:
            qs = qs.filter(activity_type=activity_type)

        allowed_ordering = {
            "created_at",
            "-created_at",
            "id",
            "-id",
        }

        if ordering not in allowed_ordering:
            ordering = "-created_at"

        return qs.order_by(ordering, "-id")
