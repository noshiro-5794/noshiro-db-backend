from rest_framework import serializers

from apps.community.models import UserBlock, UserMute


class RelationshipReasonRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=256,
    )


class RelationshipUserResponseSerializer(serializers.Serializer):
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


class UserBlockResponseSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = UserBlock
        fields = [
            "user",
            "reason",
            "created_at",
        ]

    def get_user(self, obj):
        return RelationshipUserResponseSerializer(obj.blocked_user).data


class UserMuteResponseSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = UserMute
        fields = [
            "user",
            "reason",
            "created_at",
        ]

    def get_user(self, obj):
        return RelationshipUserResponseSerializer(obj.muted_user).data
