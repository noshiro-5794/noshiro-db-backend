from rest_framework import serializers

from apps.community.models import CommunityBookmark, CommunityReaction
from apps.community.selectors.target_selector import CommunityTargetSelector


class CommunityReactionRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(
        choices=sorted(CommunityTargetSelector.REACTION_TARGETS)
    )
    target_id = serializers.IntegerField(min_value=1)
    reaction_type = serializers.ChoiceField(
        choices=CommunityReaction.ReactionType.choices,
        default=CommunityReaction.ReactionType.LIKE,
    )


class CommunityReactionDeleteRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(
        choices=sorted(CommunityTargetSelector.REACTION_TARGETS)
    )
    target_id = serializers.IntegerField(min_value=1)
    reaction_type = serializers.ChoiceField(
        choices=CommunityReaction.ReactionType.choices,
        default=CommunityReaction.ReactionType.LIKE,
    )


class CommunityReactionResponseSerializer(serializers.ModelSerializer):
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = CommunityReaction
        fields = [
            "id",
            "target_type",
            "target_id",
            "reaction_type",
            "created_at",
        ]

    def get_target_type(self, obj):
        for target_type in CommunityTargetSelector.REACTION_TARGETS:
            if getattr(obj, f"{target_type}_id", None):
                return target_type
        return ""

    def get_target_id(self, obj):
        target_type = self.get_target_type(obj)
        if not target_type:
            return None
        return getattr(obj, f"{target_type}_id")


class CommunityBookmarkRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(
        choices=sorted(CommunityTargetSelector.BOOKMARK_TARGETS)
    )
    target_id = serializers.IntegerField(min_value=1)


class CommunityBookmarkResponseSerializer(serializers.ModelSerializer):
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = CommunityBookmark
        fields = [
            "id",
            "target_type",
            "target_id",
            "created_at",
        ]

    def get_target_type(self, obj):
        for target_type in CommunityTargetSelector.BOOKMARK_TARGETS:
            if getattr(obj, f"{target_type}_id", None):
                return target_type
        return ""

    def get_target_id(self, obj):
        target_type = self.get_target_type(obj)
        if not target_type:
            return None
        return getattr(obj, f"{target_type}_id")
