from rest_framework import serializers

from apps.index.models import Subject
from apps.users.models import Collection, Review, UserSubject


class PublicUserSubjectListRequestSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        required=False,
        choices=UserSubject.Status.choices,
    )
    subject_type = serializers.ChoiceField(
        required=False,
        choices=Subject.SubjectType.choices,
    )
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="-id",
        choices=(
            "id",
            "-id",
            "simple_rating",
            "-simple_rating",
            "rating",
            "-rating",
            "watch_start_date",
            "-watch_start_date",
            "watch_end_date",
            "-watch_end_date",
        ),
    )


class PublicReviewListRequestSerializer(serializers.Serializer):
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="-id",
        choices=("id", "-id", "created_at", "-created_at"),
    )


class PublicCollectionListRequestSerializer(serializers.Serializer):
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="-id",
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


class PublicUserProfileResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nickname = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    is_following = serializers.SerializerMethodField()

    def get_nickname(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return ""

        return getattr(profile, "nickname", "") or ""

    def get_avatar(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return ""

        avatar = getattr(profile, "avatar", "")

        if not avatar:
            return ""

        if hasattr(avatar, "url"):
            return avatar.url

        return str(avatar)

    def get_bio(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return ""

        return getattr(profile, "bio", "") or ""

    def get_stats(self, obj):
        return {
            "subject_count": getattr(obj, "public_subject_count", 0),
            "review_count": getattr(obj, "public_review_count", 0),
            "collection_count": getattr(obj, "collection_count", 0),
            "following_count": getattr(obj, "following_count", 0),
            "follower_count": getattr(obj, "follower_count", 0),
        }

    def get_is_following(self, obj):
        request = self.context.get("request")

        if not request:
            return False

        if not request.user or not request.user.is_authenticated:
            return False

        return bool(getattr(obj, "is_following", False))


class PublicUserSubjectResponseSerializer(serializers.ModelSerializer):
    subject = serializers.SerializerMethodField()

    class Meta:
        model = UserSubject
        fields = [
            "id",
            "subject",
            "status",
            "simple_rating",
            "rating",
            "comment",
            "watch_start_date",
            "watch_end_date",
        ]

    def get_subject(self, obj):
        subject = obj.subject

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


class PublicReviewResponseSerializer(serializers.ModelSerializer):
    subject = serializers.SerializerMethodField()
    user_subject = serializers.SerializerMethodField()
    reaction_count = serializers.IntegerField(read_only=True)
    viewer_state = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "title",
            "content",
            "is_spoiler",
            "created_at",
            "reaction_count",
            "subject",
            "user_subject",
            "viewer_state",
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
            "platform": subject.platform,
            "nsfw": subject.nsfw,
        }

    def get_user_subject(self, obj):
        user_subject = obj.user_subject

        return {
            "id": user_subject.id,
            "status": user_subject.status,
            "simple_rating": user_subject.simple_rating,
            "rating": user_subject.rating,
            "comment": user_subject.comment,
        }

    def get_viewer_state(self, obj):
        return {
            "has_liked": bool(getattr(obj, "viewer_has_liked", False)),
            "has_bookmarked": bool(getattr(obj, "viewer_has_bookmarked", False)),
        }


class PublicCollectionResponseSerializer(serializers.ModelSerializer):
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
            "item_count",
            "reaction_count",
            "viewer_state",
        ]

    def get_viewer_state(self, obj):
        return {
            "has_liked": bool(getattr(obj, "viewer_has_liked", False)),
            "has_bookmarked": bool(getattr(obj, "viewer_has_bookmarked", False)),
        }
