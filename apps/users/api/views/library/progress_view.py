from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.core.response import success_response
from apps.users.selectors.library.progress_selector import EpisodeProgressSelector
from apps.users.services.library.progress_service import EpisodeProgressService
from apps.users.api.serializers.library.progress_serializer import (
    EpisodeProgressReplaceRequestSerializer,
    EpisodeProgressPatchRequestSerializer,
    EpisodeProgressResponseSerializer,
)


class MySubjectEpisodeProgressView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, subject_id):
        data = EpisodeProgressSelector.get_progress_summary(
            user=request.user,
            subject_id=subject_id,
        )

        serializer = EpisodeProgressResponseSerializer(data)

        return success_response(data=serializer.data)

    def put(self, request, subject_id):
        serializer = EpisodeProgressReplaceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = EpisodeProgressService.replace_episode_progress(
            user=request.user,
            subject_id=subject_id,
            finished_episode_ids=serializer.validated_data["finished_episode_ids"],
        )

        output_serializer = EpisodeProgressResponseSerializer(data)

        return success_response(data=output_serializer.data)


class MySubjectEpisodeProgressItemView(APIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, subject_id, episode_id):
        serializer = EpisodeProgressPatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = EpisodeProgressService.set_episode_finished(
            user=request.user,
            subject_id=subject_id,
            episode_id=episode_id,
            is_finished=serializer.validated_data["is_finished"],
        )

        output_serializer = EpisodeProgressResponseSerializer(data)

        return success_response(data=output_serializer.data)
