from rest_framework import serializers

from apps.index.constants import PRIMARY_SUBJECT_TYPES
from apps.index.models import Subject

DISPLAY_CREDIT_KEYS = [
    {"監督", "导演", "director"},
    {"原作", "原案"},
    {"キャラクターデザイン", "人物設定", "角色设计", "人设"},
]


class OptionalBooleanField(serializers.BooleanField):
    default_empty_html = serializers.empty


def first_infobox_value(subject, keys):
    infobox = subject.infobox if isinstance(subject.infobox, list) else []
    for item in infobox:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key not in keys:
            continue
        value = item.get("value")
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry:
                    return entry
        if isinstance(value, str) and value:
            return value
    return None


def build_subject_display_meta(subject):
    parts = []
    episode_count = subject.total_episodes or subject.eps

    if episode_count:
        parts.append(f"{episode_count}话")
    elif subject.volumes:
        parts.append(f"{subject.volumes}卷")

    if subject.date:
        parts.append(f"{subject.date.year}年{subject.date.month}月{subject.date.day}日")

    for keys in DISPLAY_CREDIT_KEYS:
        value = first_infobox_value(subject, keys)
        if value and value not in parts:
            parts.append(value)

    return parts


def build_subject_display_subtitle(subject):
    return " / ".join(build_subject_display_meta(subject))


class SubjectListQuerySerializer(serializers.Serializer):
    keyword = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    subject_type = serializers.ChoiceField(
        required=False,
        choices=[
            (subject_type, Subject.SubjectType(subject_type).label)
            for subject_type in PRIMARY_SUBJECT_TYPES
        ],
    )
    nsfw = OptionalBooleanField(required=False)
    year = serializers.IntegerField(required=False, min_value=1900, max_value=2100)
    season = serializers.ChoiceField(
        required=False,
        choices=["winter", "spring", "summer", "fall"],
    )
    platform = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    source_id = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=64,
    )
    source = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=64,
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    episodes_min = serializers.IntegerField(required=False, min_value=0)
    episodes_max = serializers.IntegerField(required=False, min_value=0)
    ordering = serializers.ChoiceField(
        required=False,
        choices=[
            "date",
            "-date",
            "title",
            "-title",
            "updated_at",
            "-updated_at",
            "created_at",
            "-created_at",
        ],
    )

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                {"date_to": "date_to must not be earlier than date_from."}
            )

        episodes_min = attrs.get("episodes_min")
        episodes_max = attrs.get("episodes_max")
        if (
            episodes_min is not None
            and episodes_max is not None
            and episodes_min > episodes_max
        ):
            raise serializers.ValidationError(
                {"episodes_max": "episodes_max must be at least episodes_min."}
            )
        return attrs


class SubjectListResponseSerializer(serializers.ModelSerializer):
    display_title = serializers.SerializerMethodField()
    title_original = serializers.CharField(source="title")
    title_localized = serializers.CharField(source="title_cn")
    year = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    display_meta = serializers.SerializerMethodField()
    display_subtitle = serializers.SerializerMethodField()
    description_excerpt = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    content = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            "id",
            "subject_type",
            "title",
            "title_cn",
            "date",
            "image_thumbnail",
            "platform",
            "nsfw",
            "series",
            "volumes",
            "eps",
            "total_episodes",
            "display_title",
            "title_original",
            "title_localized",
            "year",
            "images",
            "display_meta",
            "display_subtitle",
            "description_excerpt",
            "source",
            "content",
        ]

    def get_display_title(self, obj):
        return obj.title or obj.title_cn or "Untitled"

    def get_year(self, obj):
        return obj.date.year if obj.date else None

    def get_images(self, obj):
        return {
            "poster": obj.image_thumbnail or obj.image_original or "",
            "thumbnail": obj.image_thumbnail or "",
            "original": obj.image_original or "",
        }

    def get_display_meta(self, obj):
        return build_subject_display_meta(obj)

    def get_display_subtitle(self, obj):
        return build_subject_display_subtitle(obj)

    def get_description_excerpt(self, obj):
        description = (obj.description or "").strip()
        if len(description) <= 180:
            return description
        return f"{description[:177].rstrip()}..."

    def get_source(self, obj):
        return {
            "provider": obj.info_source,
            "id": obj.id_source,
        }

    def get_content(self, obj):
        return {
            "series": obj.series,
            "episodes": obj.total_episodes or obj.eps,
            "volumes": obj.volumes,
        }


class SubjectDetailResponseSerializer(SubjectListResponseSerializer):
    episode_count = serializers.IntegerField(read_only=True)
    staff_count = serializers.IntegerField(read_only=True)
    character_count = serializers.IntegerField(read_only=True)
    image_original = serializers.URLField()
    description = serializers.CharField()
    infobox = serializers.JSONField()
    tags = serializers.JSONField()

    class Meta(SubjectListResponseSerializer.Meta):
        fields = [
            *SubjectListResponseSerializer.Meta.fields,
            "image_original",
            "description",
            "infobox",
            "tags",
            "episode_count",
            "staff_count",
            "character_count",
        ]
