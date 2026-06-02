from rest_framework import serializers


class EpisodeProgressReplaceRequestSerializer(serializers.Serializer):

    finished_episode_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
    )

    def validate_finished_episode_ids(self, value):
        seen = set()
        result = []
        for episode_id in value:
            if episode_id not in seen:
                seen.add(episode_id)
                result.append(episode_id)
        return result


class EpisodeProgressPatchRequestSerializer(serializers.Serializer):

    is_finished = serializers.BooleanField()


class EpisodeProgressEpisodeSerializer(serializers.Serializer):

    id = serializers.IntegerField()
    title = serializers.CharField()
    type = serializers.CharField()
    ep_num = serializers.IntegerField(allow_null=True)
    sort = serializers.IntegerField(allow_null=True)
    date = serializers.DateField(allow_null=True)
    is_finished = serializers.BooleanField()


class EpisodeProgressResponseSerializer(serializers.Serializer):

    subject_id = serializers.UUIDField()
    user_subject_id = serializers.IntegerField(allow_null=True)
    total_episodes = serializers.IntegerField()
    finished_count = serializers.IntegerField()
    finished_episode_ids = serializers.ListField(child=serializers.IntegerField())
    episodes = EpisodeProgressEpisodeSerializer(many=True)
