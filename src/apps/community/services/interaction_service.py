from django.db import transaction
from django.db.models import F

from apps.community.exceptions import (
    CommunityBookmarkNotFound,
    CommunityReactionNotFound,
    CommunityTargetInvalid,
)
from apps.community.models import (
    Activity,
    CommunityBookmark,
    CommunityComment,
    CommunityPost,
    CommunityReaction,
)
from apps.community.selectors.target_selector import CommunityTargetSelector
from apps.community.services.notification_service import NotificationService
from apps.users.models import Collection, Review


class CommunityInteractionService:
    @staticmethod
    def _target_kwargs(*, target_type: str, target):
        return {target_type: target}

    @staticmethod
    def _bump_reaction_count(*, target, delta: int):
        model = None

        if isinstance(target, CommunityPost):
            model = CommunityPost
        elif isinstance(target, CommunityComment):
            model = CommunityComment

        if model is not None:
            qs = model.objects.filter(id=target.id)
            if delta < 0:
                qs = qs.filter(reaction_count__gt=0)
            qs.update(reaction_count=F("reaction_count") + delta)

    @staticmethod
    def _reaction_notification_kwargs(target):
        if isinstance(target, CommunityPost):
            return {"post": target}
        if isinstance(target, CommunityComment):
            return {"comment": target}
        if isinstance(target, Review):
            return {"review": target}
        if isinstance(target, Collection):
            return {"collection": target}
        if isinstance(target, Activity):
            return {"activity": target}
        return {}

    @staticmethod
    @transaction.atomic
    def react(
        *,
        user,
        target_type: str,
        target_id: int,
        reaction_type=CommunityReaction.ReactionType.LIKE,
    ):
        target = CommunityTargetSelector.get_target_or_raise(
            target_type=target_type,
            target_id=target_id,
            allowed_targets=CommunityTargetSelector.REACTION_TARGETS,
            actor=user,
        )

        reaction, created = CommunityReaction.objects.get_or_create(
            user=user,
            reaction_type=reaction_type,
            **CommunityInteractionService._target_kwargs(
                target_type=target_type,
                target=target,
            ),
        )

        if created:
            CommunityInteractionService._bump_reaction_count(target=target, delta=1)
            NotificationService.create_reacted_notification(
                recipient=CommunityTargetSelector.owner_for_target(target),
                actor=user,
                reaction_type=reaction_type,
                **CommunityInteractionService._reaction_notification_kwargs(target),
            )

        return reaction, created

    @staticmethod
    @transaction.atomic
    def unreact(
        *,
        user,
        target_type: str,
        target_id: int,
        reaction_type=CommunityReaction.ReactionType.LIKE,
    ):
        target = CommunityTargetSelector.get_target_or_raise(
            target_type=target_type,
            target_id=target_id,
            allowed_targets=CommunityTargetSelector.REACTION_TARGETS,
            actor=user,
        )
        deleted_count, _ = CommunityReaction.objects.filter(
            user=user,
            reaction_type=reaction_type,
            **CommunityInteractionService._target_kwargs(
                target_type=target_type,
                target=target,
            ),
        ).delete()

        if deleted_count == 0:
            raise CommunityReactionNotFound()

        CommunityInteractionService._bump_reaction_count(target=target, delta=-1)

    @staticmethod
    @transaction.atomic
    def bookmark(*, user, target_type: str, target_id: int):
        if target_type not in CommunityTargetSelector.BOOKMARK_TARGETS:
            raise CommunityTargetInvalid()

        target = CommunityTargetSelector.get_target_or_raise(
            target_type=target_type,
            target_id=target_id,
            allowed_targets=CommunityTargetSelector.BOOKMARK_TARGETS,
            actor=user,
        )

        bookmark, created = CommunityBookmark.objects.get_or_create(
            user=user,
            **CommunityInteractionService._target_kwargs(
                target_type=target_type,
                target=target,
            ),
        )

        return bookmark, created

    @staticmethod
    @transaction.atomic
    def unbookmark(*, user, target_type: str, target_id: int):
        if target_type not in CommunityTargetSelector.BOOKMARK_TARGETS:
            raise CommunityTargetInvalid()

        target = CommunityTargetSelector.get_target_or_raise(
            target_type=target_type,
            target_id=target_id,
            allowed_targets=CommunityTargetSelector.BOOKMARK_TARGETS,
            actor=user,
        )
        deleted_count, _ = CommunityBookmark.objects.filter(
            user=user,
            **CommunityInteractionService._target_kwargs(
                target_type=target_type,
                target=target,
            ),
        ).delete()

        if deleted_count == 0:
            raise CommunityBookmarkNotFound()
