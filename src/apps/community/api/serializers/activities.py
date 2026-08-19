from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.community.api.serializers.common import (
    CommunityUserResponseSerializer,
)
from apps.community.api.serializers.contracts import (
    ActivityCollectionItemSerializer,
    ActivityCollectionSerializer,
    ActivityCommentSerializer,
    ActivityLibraryEntrySerializer,
    ActivityPostSerializer,
    ActivityReviewSerializer,
    LikeViewerStateSerializer,
)
from apps.community.models import Activity
from apps.index.api.serializers.knowledge import EntitySummarySerializer


class ActivityListRequestSerializer(serializers.Serializer):
    activity_type = serializers.ChoiceField(
        required=False,
        choices=Activity.ActivityType.choices,
    )
    ordering = serializers.ChoiceField(
        required=False,
        default="-created_at",
        choices=("created_at", "-created_at", "id", "-id"),
    )


class FeedListRequestSerializer(ActivityListRequestSerializer):
    include_self = serializers.BooleanField(required=False, default=False)


class ActivityResponseSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    target_user = serializers.SerializerMethodField()
    library_entry = serializers.SerializerMethodField()
    entity = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    collection = serializers.SerializerMethodField()
    collection_item = serializers.SerializerMethodField()
    post = serializers.SerializerMethodField()
    comment = serializers.SerializerMethodField()
    reaction_count = serializers.IntegerField(read_only=True)
    viewer_state = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = [
            "id",
            "activity_type",
            "user",
            "target_user",
            "library_entry",
            "entity",
            "review",
            "collection",
            "collection_item",
            "post",
            "comment",
            "message",
            "visibility",
            "feed_policy",
            "reaction_count",
            "viewer_state",
            "group_key",
            "dedupe_key",
            "created_at",
        ]

    @extend_schema_field(CommunityUserResponseSerializer(allow_null=True))
    def get_user(self, obj):
        if not obj.user:
            return None

        return CommunityUserResponseSerializer(obj.user).data

    @extend_schema_field(CommunityUserResponseSerializer(allow_null=True))
    def get_target_user(self, obj):
        if not obj.target_user:
            return None

        return CommunityUserResponseSerializer(obj.target_user).data

    @extend_schema_field(ActivityLibraryEntrySerializer(allow_null=True))
    def get_library_entry(self, obj):
        user_subject = obj.user_subject

        if not user_subject:
            return None

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

    @extend_schema_field(EntitySummarySerializer(allow_null=True))
    def get_entity(self, obj):
        entity = obj.entity
        if not entity and obj.user_subject:
            entity = obj.user_subject.entity
        elif not entity and obj.collection_item and obj.collection_item.user_subject:
            entity = obj.collection_item.user_subject.entity
        elif not entity and obj.review and obj.review.user_subject:
            entity = obj.review.user_subject.entity
        elif not entity and obj.post:
            entity = obj.post.entity
        if not entity:
            return None
        from apps.index.selectors.projections import entity_summary

        return entity_summary(entity, safe=True)

    @extend_schema_field(ActivityReviewSerializer(allow_null=True))
    def get_review(self, obj):
        review = obj.review

        if not review:
            return None

        return {
            "id": review.id,
            "title": review.title,
            "content": review.content,
            "is_public": review.is_public,
            "is_spoiler": review.is_spoiler,
            "created_at": review.created_at,
        }

    @extend_schema_field(ActivityCollectionSerializer(allow_null=True))
    def get_collection(self, obj):
        collection = obj.collection

        if not collection:
            return None

        return {
            "id": collection.id,
            "name": collection.name,
            "simple_rating": collection.simple_rating,
            "note": collection.note,
            "is_public": collection.is_public,
        }

    @extend_schema_field(ActivityCollectionItemSerializer(allow_null=True))
    def get_collection_item(self, obj):
        collection_item = obj.collection_item

        if not collection_item:
            return None

        return {
            "id": collection_item.id,
            "order": collection_item.order,
            "relation": collection_item.relation,
        }

    @extend_schema_field(ActivityPostSerializer(allow_null=True))
    def get_post(self, obj):
        post = obj.post

        if not post:
            return None

        return {
            "id": post.id,
            "content": post.content,
            "visibility": post.visibility,
            "is_spoiler": post.is_spoiler,
            "is_nsfw": post.is_nsfw,
            "created_at": post.created_at,
        }

    @extend_schema_field(ActivityCommentSerializer(allow_null=True))
    def get_comment(self, obj):
        comment = obj.comment

        if not comment:
            return None

        return {
            "id": comment.id,
            "content": comment.content,
            "visibility": comment.visibility,
            "is_spoiler": comment.is_spoiler,
            "created_at": comment.created_at,
        }

    @extend_schema_field(LikeViewerStateSerializer)
    def get_viewer_state(self, obj):
        return {
            "has_liked": bool(getattr(obj, "viewer_has_liked", False)),
        }
