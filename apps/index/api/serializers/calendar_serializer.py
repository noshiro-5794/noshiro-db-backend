from rest_framework import serializers

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
    image_thumbnail = serializers.CharField(source="subject.image_thumbnail")
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
            "image_thumbnail",
            "platform",
            "nsfw",
            "weekday_en",
            "doing",
        ]
