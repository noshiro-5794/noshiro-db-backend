from django.db import transaction

from apps.index.exceptions import InvalidEpisodeIds, SubjectNotFound
from apps.index.models import Episode, Subject
from apps.users.exceptions import UserSubjectNotFound
from apps.users.models import UserEpisodeProgress, UserSubject
from apps.users.selectors.library.progress_selector import EpisodeProgressSelector


class EpisodeProgressService:
    @staticmethod
    def _get_subject_or_raise(*, subject_id):
        try:
            return Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist as exc:
            raise SubjectNotFound() from exc

    @staticmethod
    def _get_user_subject_or_raise(*, user, subject):
        user_subject = (
            UserSubject.objects.select_for_update()
            .filter(
                user=user,
                subject=subject,
            )
            .first()
        )
        if not user_subject:
            raise UserSubjectNotFound()
        return user_subject

    @staticmethod
    def _validate_episodes_belong_to_subject(*, subject, episode_ids):
        if not episode_ids:
            return []

        valid_episode_ids = set(
            Episode.objects.filter(
                id__in=episode_ids,
                subject=subject,
                type="EP",
            ).values_list("id", flat=True)
        )

        requested_ids = list(dict.fromkeys(episode_ids))
        invalid_episode_ids = [
            episode_id
            for episode_id in requested_ids
            if episode_id not in valid_episode_ids
        ]

        if invalid_episode_ids:
            raise InvalidEpisodeIds()

        return requested_ids

    @classmethod
    @transaction.atomic
    def replace_episode_progress(cls, *, user, subject_id, finished_episode_ids):
        subject = cls._get_subject_or_raise(subject_id=subject_id)

        user_subject = cls._get_user_subject_or_raise(
            user=user,
            subject=subject,
        )

        valid_episode_ids = cls._validate_episodes_belong_to_subject(
            subject=subject,
            episode_ids=finished_episode_ids,
        )

        UserEpisodeProgress.objects.filter(
            user_subject=user_subject,
        ).delete()

        UserEpisodeProgress.objects.bulk_create(
            [
                UserEpisodeProgress(
                    user_subject=user_subject,
                    episode_id=episode_id,
                    is_finished=True,
                )
                for episode_id in valid_episode_ids
            ]
        )

        return EpisodeProgressSelector.get_progress_summary(
            user=user,
            subject_id=subject_id,
        )

    @classmethod
    @transaction.atomic
    def set_episode_finished(cls, *, user, subject_id, episode_id, is_finished):
        subject = cls._get_subject_or_raise(subject_id=subject_id)

        user_subject = cls._get_user_subject_or_raise(
            user=user,
            subject=subject,
        )

        cls._validate_episodes_belong_to_subject(
            subject=subject,
            episode_ids=[episode_id],
        )

        if is_finished:
            UserEpisodeProgress.objects.update_or_create(
                user_subject=user_subject,
                episode_id=episode_id,
                defaults={
                    "is_finished": True,
                },
            )
        else:
            UserEpisodeProgress.objects.filter(
                user_subject=user_subject,
                episode_id=episode_id,
            ).delete()

        return EpisodeProgressSelector.get_progress_summary(
            user=user,
            subject_id=subject_id,
        )
