from rest_framework import serializers


class CommunityUserResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nickname = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    def get_nickname(self, obj) -> str:
        profile = getattr(obj, "profile", None)
        return getattr(profile, "nickname", "") or ""

    def get_avatar(self, obj) -> str:
        profile = getattr(obj, "profile", None)
        avatar = getattr(profile, "avatar", "") or ""
        return avatar.url if hasattr(avatar, "url") else str(avatar)
