from rest_framework import serializers

from apps.users.models import UserSubjectRatingDetail


class UserSubjectRatingDetailItemSerializer(serializers.Serializer):
    key = serializers.CharField(
        max_length=256,
        trim_whitespace=True,
    )
    value = serializers.DecimalField(
        max_digits=3,
        decimal_places=1,
        min_value=0,
        max_value=10,
    )

    def validate_key(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Rating detail key can not be blank.")
        return value


class UserSubjectRatingDetailReplaceRequestSerializer(serializers.Serializer):
    details = UserSubjectRatingDetailItemSerializer(
        many=True,
        allow_empty=True,
    )

    def validate_details(self, value):
        seen = set()
        duplicate_keys = []
        for item in value:
            key = item["key"].strip()
            if key in seen:
                duplicate_keys.append(key)
            seen.add(key)
        if duplicate_keys:
            raise serializers.ValidationError(
                {
                    "duplicate_keys": duplicate_keys,
                    "message": "Duplicate rating detail keys are not allowed.",
                }
            )
        return value


class UserSubjectRatingDetailResponseSerializer(serializers.ModelSerializer):

    class Meta:
        model = UserSubjectRatingDetail
        fields = [
            "key",
            "value",
        ]
