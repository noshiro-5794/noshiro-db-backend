from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.community.api.serializers.contracts import BookmarkTargetSerializer
from apps.community.models import CommunityBookmark, CommunityReaction
from apps.community.selectors.target_selector import CommunityTargetSelector
from apps.index.selectors.projections import entity_summary


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

    @extend_schema_field(OpenApiTypes.STR)
    def get_target_type(self, obj):
        for target_type in CommunityTargetSelector.REACTION_TARGETS:
            if getattr(obj, f"{target_type}_id", None):
                return target_type
        return ""

    @extend_schema_field(OpenApiTypes.INT)
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


class CommunityBookmarkListRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(
        required=False,
        choices=sorted(CommunityTargetSelector.BOOKMARK_TARGETS),
    )
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )


class CommunityBookmarkResponseSerializer(serializers.ModelSerializer):
    target_type = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()

    class Meta:
        model = CommunityBookmark
        fields = [
            "id",
            "target_type",
            "target_id",
            "target",
            "created_at",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_target_type(self, obj):
        for target_type in CommunityTargetSelector.BOOKMARK_TARGETS:
            if getattr(obj, f"{target_type}_id", None):
                return target_type
        return ""

    @extend_schema_field(OpenApiTypes.INT)
    def get_target_id(self, obj):
        target_type = self.get_target_type(obj)
        if not target_type:
            return None
        return getattr(obj, f"{target_type}_id")

    @extend_schema_field(BookmarkTargetSerializer(allow_null=True))
    def get_target(self, obj):
        target_type = self.get_target_type(obj)

        if target_type == "post" and obj.post:
            return {
                "type": "post",
                "id": obj.post.id,
                "title": (obj.post.content or "").splitlines()[0][:96],
                "entity": (
                    entity_summary(obj.post.entity, safe=True)
                    if obj.post.entity
                    else None
                ),
                "author": self._serialize_user(obj.post.author),
                "created_at": obj.post.created_at,
            }

        if target_type == "review" and obj.review:
            user_subject = obj.review.user_subject
            user = user_subject.user if user_subject else None
            return {
                "type": "review",
                "id": obj.review.id,
                "title": obj.review.title,
                "body": obj.review.content[:240],
                "entity": (
                    entity_summary(user_subject.entity, safe=True)
                    if user_subject and user_subject.entity
                    else None
                ),
                "author": self._serialize_user(user),
                "is_spoiler": obj.review.is_spoiler,
                "created_at": obj.review.created_at,
            }

        if target_type == "collection" and obj.collection:
            return {
                "type": "collection",
                "id": obj.collection.id,
                "title": obj.collection.name,
                "body": obj.collection.note[:240],
                "author": self._serialize_user(obj.collection.user),
                "simple_rating": obj.collection.simple_rating,
            }

        return None

    def _serialize_user(self, user):
        if not user:
            return None

        profile = getattr(user, "profile", None)
        avatar = getattr(profile, "avatar", "") if profile else ""

        return {
            "id": user.id,
            "nickname": getattr(profile, "nickname", "") if profile else "",
            "avatar": avatar.url
            if avatar and hasattr(avatar, "url")
            else str(avatar or ""),
        }
