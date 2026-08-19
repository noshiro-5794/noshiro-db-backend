from rest_framework import serializers


class ReviewListRequestSerializer(serializers.Serializer):
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="-created_at",
        choices=("created_at", "-created_at", "id", "-id"),
    )


class ReviewCreateRequestSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=256,
        trim_whitespace=True,
    )
    content = serializers.CharField(
        trim_whitespace=False,
        max_length=20000,
    )
    is_public = serializers.BooleanField(
        required=False,
        default=True,
    )
    is_spoiler = serializers.BooleanField(
        required=False,
        default=False,
    )

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Review title can not be blank.")
        return value

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Review content can not be blank.")
        return value


class ReviewUpdateRequestSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=256,
        trim_whitespace=True,
        required=False,
    )
    content = serializers.CharField(
        trim_whitespace=False,
        required=False,
        max_length=20000,
    )
    is_public = serializers.BooleanField(
        required=False,
    )
    is_spoiler = serializers.BooleanField(
        required=False,
    )

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Review title can not be blank.")
        return value

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Review content can not be blank.")
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs
