from rest_framework import serializers

from apps.community.api.serializers.common import (
    CommunityUserResponseSerializer,
)
from apps.community.models import Visibility
from apps.index.api.serializers.knowledge import EntitySummarySerializer


class UpdatedCountSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField(min_value=0)


class TargetReferenceSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.IntegerField()


class LikeViewerStateSerializer(serializers.Serializer):
    has_liked = serializers.BooleanField()


class CommentViewerStateSerializer(LikeViewerStateSerializer):
    is_following_author = serializers.BooleanField()


class PostViewerStateSerializer(CommentViewerStateSerializer):
    has_bookmarked = serializers.BooleanField()


class ActivityLibraryEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    simple_rating = serializers.IntegerField(allow_null=True)
    rating = serializers.DecimalField(max_digits=3, decimal_places=1, allow_null=True)
    comment = serializers.CharField(allow_blank=True)
    watch_start_date = serializers.DateField(allow_null=True)
    watch_end_date = serializers.DateField(allow_null=True)
    is_public = serializers.BooleanField()


class ActivityReviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    content = serializers.CharField()
    is_public = serializers.BooleanField()
    is_spoiler = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ActivityCollectionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    simple_rating = serializers.IntegerField(allow_null=True)
    note = serializers.CharField(allow_blank=True)
    is_public = serializers.BooleanField()


class ActivityCollectionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    order = serializers.IntegerField()
    relation = serializers.CharField(allow_blank=True)


class ActivityPostSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    content = serializers.CharField()
    visibility = serializers.ChoiceField(choices=Visibility.choices)
    is_spoiler = serializers.BooleanField()
    is_nsfw = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ActivityCommentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    content = serializers.CharField()
    visibility = serializers.ChoiceField(choices=Visibility.choices)
    is_spoiler = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class BookmarkTargetSerializer(serializers.Serializer):
    type = serializers.CharField()
    id = serializers.IntegerField()
    title = serializers.CharField()
    body = serializers.CharField(required=False)
    entity = EntitySummarySerializer(required=False, allow_null=True)
    author = CommunityUserResponseSerializer(allow_null=True)
    is_spoiler = serializers.BooleanField(required=False)
    simple_rating = serializers.IntegerField(required=False, allow_null=True)
    created_at = serializers.DateTimeField(required=False)
