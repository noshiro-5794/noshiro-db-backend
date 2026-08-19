from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.community.api.serializers.common import (
    CommunityUserResponseSerializer,
)
from apps.community.models import Notification


class NotificationListRequestSerializer(serializers.Serializer):
    is_read = serializers.BooleanField(required=False)


class NotificationResponseSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "actor",
            "target",
            "metadata",
            "is_read",
            "read_at",
            "created_at",
        ]

    @extend_schema_field(CommunityUserResponseSerializer(allow_null=True))
    def get_actor(self, obj):
        if not obj.actor:
            return None
        return CommunityUserResponseSerializer(obj.actor).data

    def _user_summary(self, user):
        if not user:
            return None
        return CommunityUserResponseSerializer(user).data

    def _target_base(self, target_type, target_id):
        return {
            "type": target_type,
            "id": target_id,
        }

    def _post_target(self, post):
        data = self._target_base("post", post.id)
        data["author"] = self._user_summary(post.author)
        return data

    def _review_target(self, review):
        data = self._target_base("review", review.id)
        user_subject = getattr(review, "user_subject", None)
        data["author"] = self._user_summary(getattr(user_subject, "user", None))
        return data

    def _collection_target(self, collection):
        data = self._target_base("collection", collection.id)
        data["owner"] = self._user_summary(collection.user)
        return data

    def _activity_target(self, activity):
        data = self._target_base("activity", activity.id)
        data["user"] = self._user_summary(activity.user)
        data["target_user"] = self._user_summary(activity.target_user)

        if activity.post_id:
            data["post"] = self._post_target(activity.post)
        if activity.review_id:
            data["review"] = self._review_target(activity.review)
        if activity.collection_id:
            data["collection"] = self._collection_target(activity.collection)
        if activity.entity_id:
            data["entity"] = {"id": str(activity.entity_id)}
        if activity.comment_id:
            data["comment"] = self._comment_target(activity.comment)

        return data

    def _comment_target(self, comment):
        data = self._target_base("comment", comment.id)
        data["author"] = self._user_summary(comment.author)
        data["parent_id"] = comment.parent_id

        if comment.post_id:
            data["post"] = self._post_target(comment.post)
        if comment.review_id:
            data["review"] = self._review_target(comment.review)
        if comment.collection_id:
            data["collection"] = self._collection_target(comment.collection)
        if comment.activity_id:
            data["activity"] = self._activity_target(comment.activity)

        return data

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_target(self, obj):
        if obj.activity_id:
            return self._activity_target(obj.activity)
        if obj.post_id:
            return self._post_target(obj.post)
        if obj.comment_id:
            return self._comment_target(obj.comment)
        if obj.review_id:
            return self._review_target(obj.review)
        if obj.collection_id:
            return self._collection_target(obj.collection)
        return None

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_read(self, obj):
        return obj.read_at is not None


class NotificationUnreadCountResponseSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField()
