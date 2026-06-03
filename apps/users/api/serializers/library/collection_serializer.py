from rest_framework import serializers

from apps.users.models import Collection, CollectionItem


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
    )
    is_public = serializers.BooleanField(required=False)

    def validate_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Collection name can not be blank.")

        return value


class CollectionItemCreateRequestSerializer(serializers.Serializer):
    user_subject_id = serializers.IntegerField(
        required=False,
        min_value=1,
    )
    subject_id = serializers.UUIDField(required=False)
    order = serializers.IntegerField(required=False, default=0)
    relation = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=256,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        has_user_subject_id = "user_subject_id" in attrs
        has_subject_id = "subject_id" in attrs

        if has_user_subject_id == has_subject_id:
            raise serializers.ValidationError(
                "Provide exactly one of user_subject_id or subject_id."
            )

        return attrs


class CollectionItemReplaceItemSerializer(serializers.Serializer):
    user_subject_id = serializers.IntegerField(
        required=False,
        min_value=1,
    )
    subject_id = serializers.UUIDField(required=False)
    order = serializers.IntegerField(required=False, default=0)
    relation = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=256,
        trim_whitespace=True,
        default="",
    )

    def validate(self, attrs):
        has_user_subject_id = "user_subject_id" in attrs
        has_subject_id = "subject_id" in attrs

        if has_user_subject_id == has_subject_id:
            raise serializers.ValidationError(
                "Provide exactly one of user_subject_id or subject_id."
            )

        return attrs


class CollectionItemReplaceRequestSerializer(serializers.Serializer):
    items = CollectionItemReplaceItemSerializer(
        many=True,
        allow_empty=True,
    )


class CollectionItemUpdateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    order = serializers.IntegerField(required=False)
    relation = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=256,
        trim_whitespace=True,
    )


class CollectionItemUpdateRequestSerializer(serializers.Serializer):
    items = CollectionItemUpdateItemSerializer(
        many=True,
        allow_empty=False,
    )


class CollectionListResponseSerializer(serializers.ModelSerializer):
    item_count = serializers.IntegerField(read_only=True)
    reaction_count = serializers.IntegerField(read_only=True)
    viewer_state = serializers.SerializerMethodField()

    class Meta:
        model = Collection
        fields = [
            "id",
            "name",
            "simple_rating",
            "note",
            "is_public",
            "item_count",
            "reaction_count",
            "viewer_state",
        ]

    def get_viewer_state(self, obj):
        return {
            "has_liked": bool(getattr(obj, "viewer_has_liked", False)),
            "has_bookmarked": bool(getattr(obj, "viewer_has_bookmarked", False)),
        }


class CollectionDetailResponseSerializer(CollectionListResponseSerializer):
    pass


class CollectionItemResponseSerializer(serializers.ModelSerializer):
    user_subject = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField()

    class Meta:
        model = CollectionItem
        fields = [
            "id",
            "user_subject",
            "subject",
            "order",
            "relation",
        ]

    def get_user_subject(self, obj):
        user_subject = obj.user_subject

        return {
            "id": user_subject.id,
            "status": user_subject.status,
            "simple_rating": user_subject.simple_rating,
            "rating": user_subject.rating,
            "comment": user_subject.comment,
            "watch_start_date": user_subject.watch_start_date,
            "watch_end_date": user_subject.watch_end_date,
            "is_public": user_subject.is_public,
        }

    def get_subject(self, obj):
        subject = obj.user_subject.subject

        return {
            "id": subject.id,
            "subject_type": subject.subject_type,
            "title": subject.title,
            "title_cn": subject.title_cn,
            "date": subject.date,
            "image_thumbnail": subject.image_thumbnail,
            "platform": subject.platform,
            "nsfw": subject.nsfw,
        }
