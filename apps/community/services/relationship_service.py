from django.db import IntegrityError, transaction

from apps.community.exceptions import (
    BlockRelationNotFound,
    CannotBlockSelf,
    CannotMuteSelf,
    MuteRelationNotFound,
)
from apps.community.models import UserBlock, UserFollow, UserMute
from apps.community.selectors.relationship_selector import UserRelationshipSelector


class UserRelationshipService:

    @staticmethod
    @transaction.atomic
    def block_user(*, user, target_user_id: int, reason=""):
        target_user = UserRelationshipSelector.get_user_by_id_or_raise(
            user_id=target_user_id,
        )

        if user.id == target_user.id:
            raise CannotBlockSelf()

        try:
            relation, created = UserBlock.objects.get_or_create(
                user=user,
                blocked_user=target_user,
                defaults={"reason": reason},
            )
        except IntegrityError:
            relation = UserBlock.objects.get(user=user, blocked_user=target_user)
            created = False

        if not created and reason and relation.reason != reason:
            relation.reason = reason
            relation.save(update_fields=["reason"])

        UserFollow.objects.filter(follower=user, following=target_user).delete()
        UserFollow.objects.filter(follower=target_user, following=user).delete()
        UserMute.objects.filter(user=user, muted_user=target_user).delete()

        return relation, created

    @staticmethod
    @transaction.atomic
    def unblock_user(*, user, target_user_id: int):
        target_user = UserRelationshipSelector.get_user_by_id_or_raise(
            user_id=target_user_id,
        )
        deleted_count, _ = UserBlock.objects.filter(
            user=user,
            blocked_user=target_user,
        ).delete()

        if deleted_count == 0:
            raise BlockRelationNotFound()

    @staticmethod
    @transaction.atomic
    def mute_user(*, user, target_user_id: int, reason=""):
        target_user = UserRelationshipSelector.get_user_by_id_or_raise(
            user_id=target_user_id,
        )

        if user.id == target_user.id:
            raise CannotMuteSelf()

        try:
            relation, created = UserMute.objects.get_or_create(
                user=user,
                muted_user=target_user,
                defaults={"reason": reason},
            )
        except IntegrityError:
            relation = UserMute.objects.get(user=user, muted_user=target_user)
            created = False

        if not created and reason and relation.reason != reason:
            relation.reason = reason
            relation.save(update_fields=["reason"])

        return relation, created

    @staticmethod
    @transaction.atomic
    def unmute_user(*, user, target_user_id: int):
        target_user = UserRelationshipSelector.get_user_by_id_or_raise(
            user_id=target_user_id,
        )
        deleted_count, _ = UserMute.objects.filter(
            user=user,
            muted_user=target_user,
        ).delete()

        if deleted_count == 0:
            raise MuteRelationNotFound()
