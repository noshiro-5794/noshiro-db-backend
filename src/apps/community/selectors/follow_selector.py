from django.contrib.auth import get_user_model

from apps.community.models import UserFollow
from apps.users.exceptions import UserNotFound

User = get_user_model()


class UserFollowSelector:
    @staticmethod
    def get_user_by_id(*, user_id: int):
        return User.objects.filter(id=user_id).first()

    @classmethod
    def get_user_by_id_or_raise(cls, *, user_id: int):
        user = cls.get_user_by_id(user_id=user_id)

        if not user:
            raise UserNotFound()

        return user

    @staticmethod
    def is_following(*, follower, following):
        return UserFollow.objects.filter(
            follower=follower,
            following=following,
        ).exists()

    @staticmethod
    def list_following_relations(*, user):
        return (
            UserFollow.objects.select_related(
                "following",
                "following__profile",
            )
            .filter(follower=user)
            .order_by("-created_at", "-id")
        )

    @staticmethod
    def list_follower_relations(*, user):
        return (
            UserFollow.objects.select_related(
                "follower",
                "follower__profile",
            )
            .filter(following=user)
            .order_by("-created_at", "-id")
        )

    @staticmethod
    def get_follow_stats(*, user):
        return {
            "following_count": UserFollow.objects.filter(follower=user).count(),
            "follower_count": UserFollow.objects.filter(following=user).count(),
        }
