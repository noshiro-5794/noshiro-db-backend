from rest_framework import serializers

from apps.community.api.serializers.common_serializer import (
    CommunityUserResponseSerializer,
)
from apps.community.models import CommunityComment, Visibility
from apps.community.selectors.target_selector import CommunityTargetSelector


class CommunityCommentCreateRequestSerializer(serializers.Serializer):
    parent_id = serializers.IntegerField(required=False)
    content = serializers.CharField(max_length=5_000, trim_whitespace=False)
    visibility = serializers.ChoiceField(
        required=False,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    is_spoiler = serializers.BooleanField(required=False, default=False)

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Comment content can not be blank.")
        return value


class CommunityCommentUpdateRequestSerializer(serializers.Serializer):
    content = serializers.CharField(
        required=False,
        max_length=5_000,
        trim_whitespace=False,
    )
    visibility = serializers.ChoiceField(
        required=False,
        choices=Visibility.choices,
    )
    is_spoiler = serializers.BooleanField(required=False)

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Comment content can not be blank.")
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs


class CommunityCommentModerationRequestSerializer(serializers.Serializer):
    action_type = serializers.ChoiceField(choices=["hide", "lock"])
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1_000,
        trim_whitespace=False,
    )


class CommunityTargetCommentCreateRequestSerializer(
    CommunityCommentCreateRequestSerializer
):
    target_type = serializers.ChoiceField(
        choices=sorted(CommunityTargetSelector.COMMENT_TARGETS)
    )
    target_id = serializers.IntegerField(min_value=1)


class CommunityTargetCommentListRequestSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(
        choices=sorted(CommunityTargetSelector.COMMENT_TARGETS)
    )
    target_id = serializers.IntegerField(min_value=1)


class CommunityCommentResponseSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()
    viewer_state = serializers.SerializerMethodField()

    class Meta:
        model = CommunityComment
        fields = [
            "id",
            "parent_id",
            "target",
            "content",
            "visibility",
            "is_spoiler",
            "is_hidden",
            "is_locked",
            "reply_count",
            "reaction_count",
            "created_at",
            "updated_at",
            "author",
            "viewer_state",
        ]

    def get_author(self, obj):
        if obj.is_hidden:
            return None
        return CommunityUserResponseSerializer(obj.author).data

    def get_target(self, obj):
        for target_type in CommunityTargetSelector.COMMENT_TARGETS:
            target_id = getattr(obj, f"{target_type}_id", None)
            if target_id:
                return {
                    "type": target_type,
                    "id": target_id,
                }
        return None

    def get_viewer_state(self, obj):
        return {
            "has_liked": bool(getattr(obj, "viewer_has_liked", False)),
            "is_following_author": bool(
                getattr(obj, "viewer_is_following_author", False)
            ),
        }
