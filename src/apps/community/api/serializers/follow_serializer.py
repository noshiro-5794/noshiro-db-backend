from rest_framework import serializers

from apps.community.api.serializers.common_serializer import (
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

    def get_user(self, obj):
        return CommunityUserResponseSerializer(obj.follower).data
