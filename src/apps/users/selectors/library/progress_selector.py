from apps.index.exceptions import SubjectNotFound
from apps.index.models import Episode, Subject
from apps.users.models import UserEpisodeProgress, UserSubject


class EpisodeProgressSelector:
    @staticmethod
    def get_user_subject(*, user, subject_id):
        return (
            UserSubject.objects.select_related("user", "subject")
            .filter(user=user, subject_id=subject_id)
            .first()
        )

    @staticmethod
    def list_subject_episodes(*, subject_id):
        return Episode.objects.filter(subject_id=subject_id, type="EP").order_by(
            "sort", "ep_num", "id"
        )

    @staticmethod
    def get_finished_episode_ids(*, user_subject: UserSubject):
        if not user_subject:
            return []
        return list(
            UserEpisodeProgress.objects.filter(
                user_subject=user_subject,
                is_finished=True,
            )
            .order_by("episode__sort", "episode__ep_num", "episode_id")
            .values_list("episode_id", flat=True)
        )

    @classmethod
    def get_progress_summary(cls, *, user, subject_id):
        if not Subject.objects.filter(id=subject_id).exists():
            raise SubjectNotFound()

        user_subject = cls.get_user_subject(
            user=user,
            subject_id=subject_id,
        )
        finished_episode_ids = cls.get_finished_episode_ids(
            user_subject=user_subject,
        )
        finished_set = set(finished_episode_ids)
        episodes = []
        for episode in cls.list_subject_episodes(subject_id=subject_id):
            episodes.append(
                {
                    "id": episode.id,
                    "title": episode.title,
                    "type": episode.type,
                    "ep_num": episode.ep_num,
                    "sort": episode.sort,
                    "date": episode.date,
                    "is_finished": episode.id in finished_set,
                }
            )
        return {
            "subject_id": subject_id,
            "user_subject_id": user_subject.id if user_subject else None,
            "total_episodes": len(episodes),
            "finished_count": len(finished_episode_ids),
            "finished_episode_ids": finished_episode_ids,
            "episodes": episodes,
        }
