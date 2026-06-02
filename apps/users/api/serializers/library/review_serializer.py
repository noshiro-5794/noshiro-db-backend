from rest_framework import serializers

from apps.users.models import Review


class ReviewCreateRequestSerializer(serializers.Serializer):
    title = serializers.CharField(
        max_length=256,
        trim_whitespace=True,
    )
    content = serializers.CharField(
        trim_whitespace=False,
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


class ReviewListResponseSerializer(serializers.ModelSerializer):
    subject = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "title",
            "content",
            "is_public",
            "is_spoiler",
            "created_at",
            "updated_at",
            "subject",
            "user",
        ]

    def get_subject(self, obj):
        subject = obj.user_subject.subject
        return {
            "id": subject.id,
            "subject_type": subject.subject_type,
            "title": subject.title,
            "title_cn": subject.title_cn,
            "date": subject.date,
            "image_thumbnail": subject.image_thumbnail,
            "nsfw": subject.nsfw,
        }

    def get_user(self, obj):
        profile = getattr(obj.user_subject.user, "profile", None)
        return {
            "id": obj.user_subject.user.id,
            "nickname": profile.nickname if profile else obj.user_subject.user.email,
            "avatar": profile.avatar if profile else None,
        }


class ReviewDetailResponseSerializer(ReviewListResponseSerializer):
    user_subject = serializers.SerializerMethodField()

    class Meta(ReviewListResponseSerializer.Meta):
        fields = ReviewListResponseSerializer.Meta.fields + [
            "user_subject",
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
