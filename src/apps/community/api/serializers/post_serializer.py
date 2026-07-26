from rest_framework import serializers

from apps.community.api.serializers.common_serializer import (
    CommunityUserResponseSerializer,
)
from apps.community.models import CommunityPost, Visibility


class CommunitySubjectResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    subject_type = serializers.CharField()
    title = serializers.CharField()
    title_cn = serializers.CharField(allow_blank=True)
    image_thumbnail = serializers.CharField(allow_blank=True)
    nsfw = serializers.BooleanField()


class CommunityPostCreateRequestSerializer(serializers.Serializer):
    subject_id = serializers.UUIDField(required=False)
    content = serializers.CharField(max_length=10_000, trim_whitespace=False)
    visibility = serializers.ChoiceField(
        required=False,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    is_spoiler = serializers.BooleanField(required=False, default=False)
    is_nsfw = serializers.BooleanField(required=False, default=False)

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Post content can not be blank.")
        return value


class CommunityPostUpdateRequestSerializer(serializers.Serializer):
    content = serializers.CharField(
        required=False,
        max_length=10_000,
        trim_whitespace=False,
    )
    visibility = serializers.ChoiceField(
        required=False,
        choices=Visibility.choices,
    )
    is_spoiler = serializers.BooleanField(required=False)
    is_nsfw = serializers.BooleanField(required=False)

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Post content can not be blank.")
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs


class CommunityPostModerationRequestSerializer(serializers.Serializer):
    action_type = serializers.ChoiceField(choices=["hide", "lock"])
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1_000,
        trim_whitespace=False,
    )


class CommunityPostListRequestSerializer(serializers.Serializer):
    subject_id = serializers.UUIDField(required=False)
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="-last_activity_at",
        choices=(
            "created_at",
            "-created_at",
            "last_activity_at",
            "-last_activity_at",
            "reaction_count",
            "-reaction_count",
            "reply_count",
            "-reply_count",
        ),
    )


class CommunityPostResponseSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField()
    viewer_state = serializers.SerializerMethodField()

    class Meta:
        model = CommunityPost
        fields = [
            "id",
            "post_type",
            "content",
            "visibility",
            "feed_policy",
            "is_spoiler",
            "is_nsfw",
            "is_pinned",
            "is_locked",
            "reply_count",
            "reaction_count",
            "last_activity_at",
            "created_at",
            "updated_at",
            "author",
            "subject",
            "viewer_state",
        ]

    def get_author(self, obj):
        return CommunityUserResponseSerializer(obj.author).data

    def get_subject(self, obj):
        if not obj.subject:
            return None
        return CommunitySubjectResponseSerializer(obj.subject).data

    def get_viewer_state(self, obj):
        return {
            "has_liked": bool(getattr(obj, "viewer_has_liked", False)),
            "has_bookmarked": bool(getattr(obj, "viewer_has_bookmarked", False)),
            "is_following_author": bool(
                getattr(obj, "viewer_is_following_author", False)
            ),
        }
