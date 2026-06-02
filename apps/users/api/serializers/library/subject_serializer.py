from rest_framework import serializers

from apps.users.models import UserSubject


class UserSubjectCreateRequestSerializer(serializers.Serializer):

    subject_id = serializers.UUIDField()

    status = serializers.ChoiceField(
        choices=UserSubject.Status.choices,
    )

    simple_rating = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=5,
    )

    rating = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=3,
        decimal_places=1,
        min_value=0,
        max_value=10,
    )

    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=2000,
    )

    watch_start_date = serializers.DateField(
        required=False,
        allow_null=True,
    )

    watch_end_date = serializers.DateField(
        required=False,
        allow_null=True,
    )

    is_public = serializers.BooleanField(
        required=False,
        default=True,
    )

    def validate(self, attrs):
        watch_start_date = attrs.get("watch_start_date")
        watch_end_date = attrs.get("watch_end_date")
        if watch_start_date and watch_end_date and watch_start_date > watch_end_date:
            raise serializers.ValidationError(
                {
                    "watch_end_date": "watch_end_date must be greater than or equal to watch_start_date."
                }
            )
        return attrs


class UserSubjectUpdateRequestSerializer(serializers.Serializer):

    status = serializers.ChoiceField(
        choices=UserSubject.Status.choices,
        required=False,
    )

    simple_rating = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=5,
    )

    rating = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=3,
        decimal_places=1,
        min_value=0,
        max_value=10,
    )

    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=2000,
    )

    watch_start_date = serializers.CharField(
        required=False,
        allow_null=True,
    )

    watch_end_date = serializers.CharField(
        required=False,
        allow_null=True,
    )

    is_public = serializers.BooleanField(
        required=False,
    )

    def validate(self, attrs):
        watch_start_date = attrs.get("watch_start_date")
        watch_end_date = attrs.get("watch_end_date")
        if watch_start_date and watch_end_date and watch_start_date > watch_end_date:
            raise serializers.ValidationError(
                {
                    "watch_end_date": "watch_end_date must be greater than or equal to watch_start_date."
                }
            )
        return attrs


class UserSubjectListResponseSerializer(serializers.ModelSerializer):

    subject = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    class Meta:
        model = UserSubject
        fields = [
            "id",
            "status",
            "simple_rating",
            "rating",
            "comment",
            "watch_start_date",
            "watch_end_date",
            "is_public",
            "created_at",
            "updated_at",
            "subject",
            "tags",
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
            "nsfw": subject.nsfw,
        }

    def get_tags(self, obj):
        relations = getattr(obj, "tag_relations", None)
        if relations is None:
            return []
        return [
            {
                "id": relation.tag.id,
                "name": relation.tag.name,
            }
            for relation in relations.all()
        ]


class UserSubjectDetailResponseSerializer(UserSubjectListResponseSerializer):

    rating_details = serializers.SerializerMethodField()

    class Meta(UserSubjectListResponseSerializer.Meta):
        fields = UserSubjectListResponseSerializer.Meta.fields + ["rating_details"]

    def get_rating_details(self, obj):
        rating_details = getattr(obj, "rating_details", None)
        if rating_details is None:
            return []
        return [
            {
                "key": detail.key,
                "value": detail.value,
            }
            for detail in rating_details.all()
        ]


class MySubjectContextResponseSerializer(serializers.Serializer):

    is_marked = serializers.BooleanField()
    user_subject = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    rating_details = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    def get_user_subject(self, obj):
        user_subject = obj["user_subject"]
        if not user_subject:
            return None

        subject = user_subject.subject
        return {
            "id": user_subject.id,
            "status": user_subject.status,
            "simple_rating": user_subject.simple_rating,
            "rating": user_subject.rating,
            "comment": user_subject.comment,
            "watch_start_date": user_subject.watch_start_date,
            "watch_end_date": user_subject.watch_end_date,
            "is_public": user_subject.is_public,
            "created_at": user_subject.created_at,
            "updated_at": user_subject.updated_at,
            "subject": {
                "id": subject.id,
                "subject_type": subject.subject_type,
                "title": subject.title,
                "title_cn": subject.title_cn,
                "date": subject.date,
                "image_thumbnail": subject.image_thumbnail,
                "nsfw": subject.nsfw,
            },
        }

    def get_tags(self, obj):
        return [
            {
                "id": tag.id,
                "name": tag.name,
            }
            for tag in obj["tags"]
        ]

    def get_rating_details(self, obj):
        return [
            {
                "key": detail.key,
                "value": detail.value,
            }
            for detail in obj["rating_details"]
        ]

    def get_reviews(self, obj):
        return [
            {
                "id": review.id,
                "title": review.title,
                "content": review.content,
                "is_public": review.is_public,
                "is_spoiler": review.is_spoiler,
                "created_at": review.created_at,
            }
            for review in obj["reviews"]
        ]

    def get_progress(self, obj):
        return {
            "finished_count": obj["finished_count"],
            "finished_episode_ids": obj["finished_episode_ids"],
        }
