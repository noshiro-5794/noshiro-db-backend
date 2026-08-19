from rest_framework import serializers

from apps.index.api.serializers.knowledge import EntitySummarySerializer
from apps.users.models import UserRelease, UserSubject, UserSubjectRatingDetail


class AccessTokenSerializer(serializers.Serializer):
    access = serializers.CharField()


class PublicLibraryQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=UserSubject.Status.choices, required=False)


class LibraryEntryQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=UserSubject.Status.choices, required=False)


class LibraryEntryWriteSerializer(serializers.Serializer):
    entity_id = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(choices=UserSubject.Status.choices, required=False)
    simple_rating = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=5
    )
    rating = serializers.DecimalField(
        required=False,
        allow_null=True,
        max_digits=3,
        decimal_places=1,
        min_value=0,
        max_value=10,
    )
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    watch_start_date = serializers.DateField(required=False, allow_null=True)
    watch_end_date = serializers.DateField(required=False, allow_null=True)
    is_public = serializers.BooleanField(required=False)


class ReleaseStateWriteSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=UserRelease.Status.choices)
    language = serializers.CharField(required=False, allow_blank=True, max_length=35)
    platform = serializers.CharField(required=False, allow_blank=True, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    started_at = serializers.DateField(required=False, allow_null=True)
    completed_at = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if (
            attrs.get("started_at")
            and attrs.get("completed_at")
            and attrs["started_at"] > attrs["completed_at"]
        ):
            raise serializers.ValidationError(
                {"completed_at": "Must not be earlier than started_at."}
            )
        return attrs


class EpisodeProgressReplaceSerializer(serializers.Serializer):
    finished_episode_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        max_length=5000,
    )

    def validate_finished_episode_ids(self, value):
        return list(dict.fromkeys(value))


class CollectionItemWriteSerializer(serializers.Serializer):
    library_entry_id = serializers.IntegerField(min_value=1)
    order = serializers.IntegerField(required=False, default=0)
    relation = serializers.CharField(
        required=False, allow_blank=True, max_length=256, default=""
    )


class CollectionItemReplaceSerializer(serializers.Serializer):
    items = CollectionItemWriteSerializer(many=True, allow_empty=True, max_length=1000)

    def validate_items(self, value):
        entry_ids = [item["library_entry_id"] for item in value]
        if len(entry_ids) != len(set(entry_ids)):
            raise serializers.ValidationError(
                "Duplicate library entries are not allowed."
            )
        return value


class CollectionItemPatchSerializer(serializers.Serializer):
    order = serializers.IntegerField(required=False)
    relation = serializers.CharField(required=False, allow_blank=True, max_length=256)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("No fields to update.")
        return attrs


class AcceptedSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("accepted",))


class AvatarSerializer(serializers.Serializer):
    avatar = serializers.URLField()


class ReleaseStateSerializer(serializers.Serializer):
    release_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=UserRelease.Status.choices)
    language = serializers.CharField(allow_blank=True)
    platform = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    started_at = serializers.DateField(allow_null=True)
    completed_at = serializers.DateField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class LibraryEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    entity = EntitySummarySerializer()
    status = serializers.ChoiceField(choices=UserSubject.Status.choices)
    simple_rating = serializers.IntegerField(allow_null=True, min_value=1, max_value=5)
    rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=1,
        allow_null=True,
        min_value=0,
        max_value=10,
    )
    comment = serializers.CharField(allow_blank=True)
    watch_start_date = serializers.DateField(allow_null=True)
    watch_end_date = serializers.DateField(allow_null=True)
    is_public = serializers.BooleanField()
    releases = ReleaseStateSerializer(many=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class RatingDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSubjectRatingDetail
        fields = ("key", "value")


class EpisodeProgressItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    title_cn = serializers.CharField(allow_blank=True)
    type = serializers.CharField(allow_blank=True)
    number = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)
    sort = serializers.DecimalField(max_digits=8, decimal_places=2, allow_null=True)
    air_date = serializers.DateField(allow_null=True)
    is_finished = serializers.BooleanField()


class EpisodeProgressSerializer(serializers.Serializer):
    library_entry_id = serializers.IntegerField()
    entity_id = serializers.UUIDField()
    total_episodes = serializers.IntegerField(min_value=0)
    finished_count = serializers.IntegerField(min_value=0)
    finished_episode_ids = serializers.ListField(child=serializers.UUIDField())
    episodes = EpisodeProgressItemSerializer(many=True)


class UserSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nickname = serializers.CharField(allow_blank=True)
    avatar = serializers.URLField(allow_blank=True)


class ViewerStateSerializer(serializers.Serializer):
    has_liked = serializers.BooleanField()
    has_bookmarked = serializers.BooleanField()


class ReviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    content = serializers.CharField()
    is_public = serializers.BooleanField()
    is_spoiler = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    reaction_count = serializers.IntegerField(min_value=0)
    entity = EntitySummarySerializer()
    library_entry_id = serializers.IntegerField()
    user = UserSummarySerializer()
    viewer_state = ViewerStateSerializer()


class CollectionViewerStateSerializer(serializers.Serializer):
    has_liked = serializers.BooleanField()
    has_bookmarked = serializers.BooleanField()


class UserCollectionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    simple_rating = serializers.IntegerField(allow_null=True, min_value=1, max_value=5)
    note = serializers.CharField(allow_blank=True)
    is_public = serializers.BooleanField()
    item_count = serializers.IntegerField(min_value=0)
    reaction_count = serializers.IntegerField(min_value=0)
    viewer_state = CollectionViewerStateSerializer()


class CollectionItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    library_entry_id = serializers.IntegerField()
    entity = EntitySummarySerializer()
    order = serializers.IntegerField()
    relation = serializers.CharField(allow_blank=True)


class PublicUserStatsSerializer(serializers.Serializer):
    library_entry_count = serializers.IntegerField(min_value=0)
    review_count = serializers.IntegerField(min_value=0)
    collection_count = serializers.IntegerField(min_value=0)
    following_count = serializers.IntegerField(min_value=0)
    follower_count = serializers.IntegerField(min_value=0)


class PublicUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nickname = serializers.CharField(allow_blank=True)
    avatar = serializers.URLField(allow_blank=True)
    bio = serializers.CharField(allow_blank=True)
    stats = PublicUserStatsSerializer()
    is_following = serializers.BooleanField()


class ProfileStatsTotalsSerializer(serializers.Serializer):
    subjects = serializers.IntegerField(min_value=0)
    reviews = serializers.IntegerField(min_value=0)
    collections = serializers.IntegerField(min_value=0)
    marks_in_year = serializers.IntegerField(min_value=0)


class ProfileStatsDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    count = serializers.IntegerField(min_value=0)


class ProfileStatsSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    available_years = serializers.ListField(child=serializers.IntegerField())
    totals = ProfileStatsTotalsSerializer()
    mark_calendar = ProfileStatsDaySerializer(many=True)
