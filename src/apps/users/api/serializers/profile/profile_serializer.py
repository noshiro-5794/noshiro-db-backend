from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from apps.users.models import UserProfile


class ProfileStatsRequestSerializer(serializers.Serializer):
    year = serializers.IntegerField(required=False, min_value=1970)
    timezone = serializers.CharField(required=False, default="UTC", max_length=64)

    def validate_timezone(self, value):
        try:
            return ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise serializers.ValidationError("Unknown IANA timezone.") from exc

    def validate(self, attrs):
        current_year = timezone.localdate().year
        year = attrs.get("year", current_year)
        if year > current_year + 1:
            raise serializers.ValidationError(
                {"year": f"Year must be less than or equal to {current_year + 1}."}
            )
        attrs["year"] = year
        return attrs


class UserProfileUpdateRequestSerializer(serializers.Serializer):
    nickname = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=32,
    )

    bio = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
    )

    theme_color = serializers.RegexField(
        required=False,
        allow_blank=True,
        regex=r"^#[0-9a-fA-F]{6}$",
        error_messages={"invalid": "theme_color must be a hex color, e.g. #66ccff."},
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs


class UserSettingsUpdateRequestSerializer(serializers.Serializer):
    language = serializers.ChoiceField(
        required=False,
        choices=UserProfile.Language.choices,
    )

    appearance = serializers.ChoiceField(
        required=False,
        choices=UserProfile.Appearance.choices,
    )

    theme_color = serializers.RegexField(
        required=False,
        allow_blank=True,
        regex=r"^#[0-9a-fA-F]{6}$",
        error_messages={"invalid": "theme_color must be a hex color, e.g. #66ccff."},
    )

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs


class AvatarUploadRequestSerializer(serializers.Serializer):
    avatar = serializers.ImageField()

    def validate_avatar(self, avatar):
        max_size = settings.AVATAR_MAX_UPLOAD_SIZE
        if avatar.size > max_size:
            max_size_mb = max_size / 1024 / 1024
            raise serializers.ValidationError(
                f"Avatar file size must be less than or equal to {max_size_mb:.0f}MB."
            )

        content_type = getattr(avatar, "content_type", "").lower()
        allowed_content_types = settings.AVATAR_ALLOWED_CONTENT_TYPES
        if content_type not in allowed_content_types:
            allowed = ", ".join(allowed_content_types)
            raise serializers.ValidationError(
                f"Unsupported avatar content type. Allowed: {allowed}."
            )

        if hasattr(avatar, "seek"):
            avatar.seek(0)

        return avatar


class UserProfileResponseSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    is_staff = serializers.BooleanField(source="user.is_staff", read_only=True)
    is_superuser = serializers.BooleanField(
        source="user.is_superuser",
        read_only=True,
    )

    class Meta:
        model = UserProfile
        fields = [
            "user_id",
            "email",
            "is_staff",
            "is_superuser",
            "nickname",
            "bio",
            "avatar",
            "language",
            "appearance",
            "theme_color",
        ]
