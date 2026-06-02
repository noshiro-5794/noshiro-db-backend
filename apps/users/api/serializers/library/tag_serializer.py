from rest_framework import serializers

from apps.users.models import UserTag


class UserTagCreateRequestSerializer(serializers.Serializer):

    name = serializers.CharField(
        max_length=64,
        trim_whitespace=True,
    )

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Tag name can not be blank.")
        return value


class UserTagUpdateRequestSerializer(serializers.Serializer):

    name = serializers.CharField(
        max_length=64,
        trim_whitespace=True,
    )

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Tag name can not be blank.")
        return value


class UserTagResponseSerializer(serializers.ModelSerializer):

    class Meta:
        model = UserTag
        fields = [
            "id",
            "name",
        ]


class UserSubjectTagReplaceRequestSerializer(serializers.Serializer):

    tag_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
    )

    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=64, trim_whitespace=True),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs):
        if "tag_ids" not in attrs and "tag_names" not in attrs:
            raise serializers.ValidationError("tag_ids or tag_names is required.")
        return attrs

    def validate_tag_ids(self, value):
        seen = set()
        result = []
        for tag_id in value:
            if tag_id not in seen:
                seen.add(tag_id)
                result.append(tag_id)
        return result

    def validate_tag_names(self, value):
        seen = set()
        result = []
        for tag_name in value:
            tag_name = tag_name.strip()
            if not tag_name:
                raise serializers.ValidationError("Tag name can not be blank.")
            if tag_name not in seen:
                seen.add(tag_name)
                result.append(tag_name)
        return result
