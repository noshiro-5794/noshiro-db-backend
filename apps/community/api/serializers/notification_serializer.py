from rest_framework import serializers

from apps.community.models import Notification


class NotificationActorResponseSerializer(serializers.Serializer):
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


class NotificationListRequestSerializer(serializers.Serializer):
    is_read = serializers.BooleanField(required=False)


class NotificationResponseSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "actor",
            "target",
            "metadata",
            "is_read",
            "read_at",
            "created_at",
        ]

    def get_actor(self, obj):
        if not obj.actor:
            return None
        return NotificationActorResponseSerializer(obj.actor).data

    def get_target(self, obj):
        for target_type in ["activity", "post", "comment", "review", "collection"]:
            target_id = getattr(obj, f"{target_type}_id", None)
            if target_id:
                return {
                    "type": target_type,
                    "id": target_id,
                }
        return None

    def get_is_read(self, obj):
        return obj.read_at is not None


class NotificationUnreadCountResponseSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()
