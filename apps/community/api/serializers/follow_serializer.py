from rest_framework import serializers

from apps.community.models import UserFollow


class FollowUserResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nickname = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    def get_nickname(self, obj):
        profile = getattr(obj, "profile", None)
        if not profile:
            return ""
        return profile.nickname

    def get_avatar(self, obj):
        profile = getattr(obj, "profile", None)
        if not profile:
            return ""
        return profile.avatar


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
        return FollowUserResponseSerializer(obj.following).data


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
        return FollowUserResponseSerializer(obj.follower).data
