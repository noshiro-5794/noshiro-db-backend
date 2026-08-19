from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.community.api.serializers.common import (
    CommunityUserResponseSerializer,
)
from apps.community.models import UserBlock, UserMute


class RelationshipReasonRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=256,
    )


class UserBlockResponseSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = UserBlock
        fields = [
            "user",
            "reason",
            "created_at",
        ]

    @extend_schema_field(CommunityUserResponseSerializer)
    def get_user(self, obj):
        return CommunityUserResponseSerializer(obj.blocked_user).data


class UserMuteResponseSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = UserMute
        fields = [
            "user",
            "reason",
            "created_at",
        ]

    @extend_schema_field(CommunityUserResponseSerializer)
    def get_user(self, obj):
        return CommunityUserResponseSerializer(obj.muted_user).data
