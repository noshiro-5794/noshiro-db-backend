from rest_framework import serializers

from apps.index.api.serializers.subject_serializer import (
    build_subject_display_meta,
    build_subject_display_subtitle,
)
from apps.index.models import CalendarSubject


class CalendarQuerySerializer(serializers.Serializer):

    weekday_en = serializers.ChoiceField(
        required=False,
        choices=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    )


class CalendarSubjectResponseSerializer(serializers.ModelSerializer):

    subject_id = serializers.UUIDField(source="subject.id")
    subject_type = serializers.CharField(source="subject.subject_type")
    title = serializers.CharField(source="subject.title")
    title_cn = serializers.CharField(source="subject.title_cn")
    display_title = serializers.CharField(source="subject.title")
    display_meta = serializers.SerializerMethodField()
    display_subtitle = serializers.SerializerMethodField()
    date = serializers.DateField(source="subject.date")
    image_thumbnail = serializers.SerializerMethodField()
    platform = serializers.CharField(source="subject.platform")
    nsfw = serializers.BooleanField(source="subject.nsfw")
    doing = serializers.IntegerField(source="collection_doing")

    class Meta:
        model = CalendarSubject
        fields = [
            "subject_id",
            "subject_type",
            "title",
            "title_cn",
            "display_title",
            "display_meta",
            "display_subtitle",
            "date",
            "image_thumbnail",
            "platform",
            "nsfw",
            "weekday_en",
            "doing",
        ]

    def get_display_meta(self, obj):
        return build_subject_display_meta(obj.subject)

    def get_display_subtitle(self, obj):
        return build_subject_display_subtitle(obj.subject)

    def get_image_thumbnail(self, obj):
        return obj.image_url or obj.subject.image_thumbnail
