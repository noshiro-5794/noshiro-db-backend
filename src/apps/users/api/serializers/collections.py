from rest_framework import serializers


class CollectionListRequestSerializer(serializers.Serializer):
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="id",
        choices=(
            "id",
            "-id",
            "name",
            "-name",
            "simple_rating",
            "-simple_rating",
            "item_count",
            "-item_count",
        ),
    )


class CollectionCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=256,
        trim_whitespace=True,
    )
    simple_rating = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=5,
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        max_length=5000,
    )
    is_public = serializers.BooleanField(required=False, default=True)

    def validate_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Collection name can not be blank.")

        return value


class CollectionUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=256,
        trim_whitespace=True,
        required=False,
    )
    simple_rating = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=5,
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        max_length=5000,
    )
    is_public = serializers.BooleanField(required=False)

    def validate_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Collection name can not be blank.")

        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs
