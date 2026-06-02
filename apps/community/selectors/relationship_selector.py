from django.contrib.auth import get_user_model

from apps.community.models import UserBlock, UserMute
from apps.users.exceptions import UserNotFound

User = get_user_model()


class UserRelationshipSelector:

    @staticmethod
    def get_user_by_id_or_raise(*, user_id: int):
        user = User.objects.filter(id=user_id).first()

        if not user:
            raise UserNotFound()

        return user

    @staticmethod
    def is_blocked_between(*, user, target_user):
        return UserBlock.objects.filter(
            user=user,
            blocked_user=target_user,
        ).exists() or UserBlock.objects.filter(
            user=target_user,
            blocked_user=user,
        ).exists()

    @staticmethod
    def list_block_relations(*, user):
        return (
            UserBlock.objects.select_related(
                "blocked_user",
                "blocked_user__profile",
            )
            .filter(user=user)
            .order_by("-created_at", "-id")
        )

    @staticmethod
    def list_mute_relations(*, user):
        return (
            UserMute.objects.select_related(
                "muted_user",
                "muted_user__profile",
            )
            .filter(user=user)
            .order_by("-created_at", "-id")
        )
