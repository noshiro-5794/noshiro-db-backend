from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.community.api.serializers.common import (
    CommunityUserResponseSerializer,
)
from apps.community.models import UserFollow


class FollowingRelationResponseSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    followed_at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = UserFollow
        fields = [
            "user",
            "followed_at",
        ]

    @extend_schema_field(CommunityUserResponseSerializer)
    def get_user(self, obj):
        return CommunityUserResponseSerializer(obj.following).data


class FollowerRelationResponseSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    followed_at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = UserFollow
        fields = [
            "user",
            "followed_at",
        ]

    @extend_schema_field(CommunityUserResponseSerializer)
    def get_user(self, obj):
        return CommunityUserResponseSerializer(obj.follower).data
