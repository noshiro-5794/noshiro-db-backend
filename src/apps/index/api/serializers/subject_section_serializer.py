from rest_framework import serializers


def subject_summary(subject):
    return {
        "id": subject.id,
        "subject_type": subject.subject_type,
        "title": subject.title,
        "title_cn": subject.title_cn,
        "date": subject.date,
        "description": subject.description,
        "image_original": subject.image_original,
        "image_thumbnail": subject.image_thumbnail,
        "platform": subject.platform,
        "nsfw": subject.nsfw,
    }


class SubjectEpisodeResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    type = serializers.CharField()
    ep_num = serializers.IntegerField(allow_null=True)
    sort = serializers.IntegerField(allow_null=True)
    duration = serializers.DurationField(allow_null=True)
    date = serializers.DateField(allow_null=True)
    description = serializers.CharField()


class SubjectEpisodeQuerySerializer(serializers.Serializer):
    type = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=64,
    )


class SubjectStaffResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="staff.id")
    name = serializers.CharField(source="staff.name")
    role = serializers.CharField()
    description = serializers.CharField(source="staff.description")
    gender = serializers.CharField(source="staff.gender")
    birth = serializers.JSONField(source="staff.birth")
    career = serializers.JSONField(source="staff.career")
    image_original = serializers.CharField(source="staff.image_original")
    image_thumbnail = serializers.CharField(source="staff.image_thumbnail")
    infobox = serializers.JSONField(source="staff.infobox")
    type = serializers.CharField(source="staff.type")


class SubjectCharacterResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="character.id")
    name = serializers.CharField(source="character.name")
    role = serializers.CharField()
    description = serializers.CharField(source="character.description")
    gender = serializers.CharField(source="character.gender")
    birth = serializers.JSONField(source="character.birth")
    blood_type = serializers.CharField(source="character.blood_type")
    image_original = serializers.CharField(source="character.image_original")
    image_thumbnail = serializers.CharField(source="character.image_thumbnail")
    infobox = serializers.JSONField(source="character.infobox")
    type = serializers.CharField(source="character.type")
    actors = serializers.SerializerMethodField()

    def get_actors(self, obj):
        actor_relations = getattr(obj.character, "subject_actor_relations", ())

        return [
            {
                "id": relation.actor.id,
                "name": relation.actor.name,
                "role": "voice",
                "description": relation.actor.description,
                "gender": relation.actor.gender,
                "birth": relation.actor.birth,
                "career": relation.actor.career,
                "image_original": relation.actor.image_original,
                "image_thumbnail": relation.actor.image_thumbnail,
                "infobox": relation.actor.infobox,
                "type": relation.actor.type,
            }
            for relation in actor_relations
        ]


class SubjectStaffRoleListResponseSerializer(serializers.Serializer):
    roles = serializers.ListField(child=serializers.CharField())


class SubjectStaffQuerySerializer(serializers.Serializer):
    role = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        max_length=256,
    )


class SubjectRelationResponseSerializer(serializers.Serializer):
    direction = serializers.ChoiceField(choices=("outgoing", "incoming"))
    relation = serializers.CharField()
    subject = serializers.DictField()


def serialize_subject_relation(relation, *, subject_id):
    is_outgoing = relation.source_id == subject_id
    return {
        "direction": "outgoing" if is_outgoing else "incoming",
        "relation": relation.relation,
        "subject": subject_summary(relation.target if is_outgoing else relation.source),
    }
