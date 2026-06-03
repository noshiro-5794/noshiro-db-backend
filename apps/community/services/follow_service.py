from django.db import IntegrityError, transaction

from apps.community.exceptions import (
    CannotFollowBlockedUser,
    CannotFollowSelf,
    FollowRelationNotFound,
)
from apps.community.models import Activity, UserFollow
from apps.community.selectors.follow_selector import UserFollowSelector
from apps.community.selectors.relationship_selector import UserRelationshipSelector
from apps.community.services.activity_service import ActivityService
from apps.community.services.notification_service import NotificationService


class UserFollowService:

    @staticmethod
    @transaction.atomic
    def follow_user(*, follower, target_user_id: int):
        following = UserFollowSelector.get_user_by_id_or_raise(
            user_id=target_user_id,
        )

        if follower.id == following.id:
            raise CannotFollowSelf()

        if UserRelationshipSelector.is_blocked_between(
            user=follower,
            target_user=following,
        ):
            raise CannotFollowBlockedUser()

        try:
            relation, created = UserFollow.objects.get_or_create(
                follower=follower,
                following=following,
            )
        except IntegrityError:
            relation = UserFollow.objects.get(
                follower=follower,
                following=following,
            )
            created = False

        if created:
            activity = ActivityService.create_user_followed_activity(
                follower=follower,
                following=following,
            )
            NotificationService.create_followed_notification(
                recipient=following,
                actor=follower,
                activity=activity,
            )

        return relation, created

    @staticmethod
    @transaction.atomic
    def unfollow_user(*, follower, target_user_id: int):
        following = UserFollowSelector.get_user_by_id_or_raise(
            user_id=target_user_id,
        )

        deleted_count, _ = UserFollow.objects.filter(
            follower=follower,
            following=following,
        ).delete()

        if deleted_count == 0:
            raise FollowRelationNotFound()

        Activity.objects.filter(
            activity_type=Activity.ActivityType.USER_FOLLOWED,
            user=follower,
            target_user=following,
            dedupe_key=f"user_followed:{follower.id}:{following.id}",
        ).delete()
