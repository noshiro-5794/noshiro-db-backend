from rest_framework import serializers

from apps.index.models import (
    ContentSafety,
    Entity,
    EntityName,
    MediaAsset,
    Release,
    Work,
)


class IndexCollectionSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    name = serializers.CharField()


class EntityQuerySerializer(serializers.Serializer):
    query = serializers.CharField(required=False, allow_blank=True, max_length=200)
    collection = serializers.SlugField(required=False, allow_blank=True)
    scope = serializers.ChoiceField(
        required=False,
        choices=("index", "all"),
        default="index",
    )


class FieldProvenanceSerializer(serializers.Serializer):
    provider = serializers.SlugField()
    namespace = serializers.SlugField()
    external_id = serializers.CharField()
    observation_id = serializers.UUIDField(allow_null=True)
    revision_id = serializers.UUIDField(allow_null=True)
    observed_at = serializers.DateTimeField(allow_null=True)


class EntityMediaSerializer(serializers.Serializer):
    url = serializers.URLField()
    purpose = serializers.CharField(allow_blank=True)
    safety = serializers.ChoiceField(choices=MediaAsset.Safety.choices)
    provenance = FieldProvenanceSerializer(allow_null=True)


class EntitySummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    entity_type = serializers.ChoiceField(choices=Entity.Kind.choices)
    lifecycle = serializers.ChoiceField(choices=Entity.Lifecycle.choices)
    audience = serializers.ChoiceField(choices=Entity.Audience.choices)
    work_type = serializers.ChoiceField(
        choices=Work.WorkType.choices,
        allow_null=True,
    )
    display_name = serializers.CharField()
    collections = serializers.ListField(child=serializers.SlugField())
    media = EntityMediaSerializer(many=True)


class EntityNameSerializer(serializers.Serializer):
    text = serializers.CharField()
    language = serializers.CharField(allow_blank=True)
    script = serializers.CharField(allow_blank=True)
    region = serializers.CharField(allow_blank=True)
    kind = serializers.ChoiceField(choices=EntityName.Kind.choices)
    is_official = serializers.BooleanField()
    is_original = serializers.BooleanField()
    is_machine_generated = serializers.BooleanField()
    is_reviewed = serializers.BooleanField()
    provenance = FieldProvenanceSerializer(allow_null=True)


class EntityDescriptionSerializer(serializers.Serializer):
    text = serializers.CharField()
    language = serializers.CharField(allow_blank=True)
    is_official = serializers.BooleanField()
    is_machine_generated = serializers.BooleanField()
    is_reviewed = serializers.BooleanField()
    spoiler_level = serializers.IntegerField(min_value=0, max_value=3)
    safety = serializers.ChoiceField(choices=ContentSafety.choices)
    provenance = FieldProvenanceSerializer(allow_null=True)


class FactEvidenceSerializer(FieldProvenanceSerializer):
    json_pointer = serializers.CharField(allow_blank=True)


class EntityFactSerializer(serializers.Serializer):
    predicate = serializers.SlugField()
    value = serializers.JSONField()
    language = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=("candidate", "selected", "rejected"))
    confidence = serializers.DecimalField(max_digits=5, decimal_places=4)
    spoiler_level = serializers.IntegerField(min_value=0, max_value=3)
    safety = serializers.ChoiceField(choices=ContentSafety.choices)
    is_machine_generated = serializers.BooleanField()
    evidence = FactEvidenceSerializer(many=True)


class EntityExternalLinkSerializer(serializers.Serializer):
    url = serializers.URLField()
    label = serializers.CharField(allow_blank=True)
    link_type = serializers.CharField(allow_blank=True)
    provenance = FieldProvenanceSerializer(allow_null=True)


class EntityContentRatingSerializer(serializers.Serializer):
    system = serializers.CharField()
    value = serializers.CharField()
    region = serializers.CharField(allow_blank=True)
    minimum_age = serializers.IntegerField(allow_null=True, min_value=0)
    provenance = FieldProvenanceSerializer()


class EntitySourceSerializer(serializers.Serializer):
    provider = serializers.SlugField()
    namespace = serializers.SlugField()
    external_id = serializers.CharField()
    url = serializers.URLField(allow_blank=True)
    mapping_kind = serializers.CharField()
    method = serializers.CharField()
    confidence = serializers.DecimalField(max_digits=5, decimal_places=4)
    last_seen_at = serializers.DateTimeField(allow_null=True)


class EntityDetailSerializer(EntitySummarySerializer):
    names = EntityNameSerializer(many=True)
    descriptions = EntityDescriptionSerializer(many=True)
    facts = EntityFactSerializer(many=True)
    external_links = EntityExternalLinkSerializer(many=True)
    content_ratings = EntityContentRatingSerializer(many=True)
    sources = EntitySourceSerializer(many=True)


class EntityRelationSerializer(serializers.Serializer):
    relation_type = serializers.SlugField()
    target = EntitySummarySerializer()
    qualifiers = serializers.JSONField()
    evidence = FactEvidenceSerializer(many=True)


class EntityCreditSerializer(serializers.Serializer):
    role = serializers.CharField()
    credited_as = serializers.CharField(allow_blank=True)
    contributor = EntitySummarySerializer()
    provenance = FieldProvenanceSerializer(allow_null=True)


class EntityEpisodeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    title_cn = serializers.CharField(allow_blank=True)
    type = serializers.CharField(allow_blank=True)
    number = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        allow_null=True,
    )
    sort = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        allow_null=True,
    )
    disc = serializers.IntegerField(allow_null=True, min_value=0)
    duration = serializers.DurationField(allow_null=True)
    raw_duration = serializers.CharField(allow_blank=True)
    air_date = serializers.DateField(allow_null=True)
    comment_count = serializers.IntegerField(allow_null=True, min_value=0)
    description = serializers.CharField(allow_blank=True)
    provenance = FieldProvenanceSerializer(allow_null=True)


class EntityCharacterSerializer(serializers.Serializer):
    role = serializers.CharField(allow_blank=True)
    spoiler_level = serializers.IntegerField(min_value=0, max_value=3)
    character = EntitySummarySerializer()
    provenance = FieldProvenanceSerializer(allow_null=True)


class EntityReleaseSerializer(serializers.Serializer):
    role = serializers.CharField()
    release = EntitySummarySerializer()
    date_start = serializers.DateField(allow_null=True)
    date_end = serializers.DateField(allow_null=True)
    date_precision = serializers.ChoiceField(choices=Release.DatePrecision.choices)
    date_raw = serializers.CharField(allow_blank=True)
    platform = serializers.CharField(allow_blank=True)
    region = serializers.CharField(allow_blank=True)
    evidence = FactEvidenceSerializer(many=True)


class EntityMetricSerializer(serializers.Serializer):
    metric = serializers.CharField()
    value = serializers.DecimalField(max_digits=20, decimal_places=6)
    sample_size = serializers.IntegerField(allow_null=True, min_value=0)
    observed_at = serializers.DateTimeField()
    provider = serializers.SlugField()


class EntityEvidenceSerializer(serializers.Serializer):
    provider = serializers.SlugField()
    namespace = serializers.SlugField()
    external_id = serializers.CharField()
    revision_id = serializers.UUIDField(allow_null=True)
    observed_at = serializers.DateTimeField()


class CalendarQuerySerializer(serializers.Serializer):
    from_ = serializers.DateTimeField(required=False, source="from")
    to = serializers.DateTimeField(required=False)
    timezone = serializers.CharField(required=False, max_length=64)


class CalendarEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    work_id = serializers.UUIDField()
    episode_id = serializers.UUIDField(allow_null=True)
    starts_at = serializers.DateTimeField(allow_null=True)
    timezone = serializers.CharField(allow_blank=True)
    region = serializers.CharField(allow_blank=True)
    weekday = serializers.IntegerField(allow_null=True, min_value=1, max_value=7)
    precision = serializers.CharField()
    raw_value = serializers.CharField(allow_blank=True)
    provenance = FieldProvenanceSerializer(allow_null=True)
