from apps.index.exceptions import SubjectNotFound
from apps.index.models import Entity
from apps.index.selectors.current import current_entity_relations
from apps.index.selectors.projections import entity_detail, preferred_name
from apps.index.services import entity_resolution_service
from apps.users.models import UserEpisodeProgress, UserSubject


class EpisodeProgressSelector:
    @staticmethod
    def get_user_subject(*, user, subject_id):
        return (
            UserSubject.objects.select_related("user", "entity")
            .filter(user=user, entity_id=subject_id)
            .first()
        )

    @staticmethod
    def list_subject_episodes(*, subject_id):
        episode_ids = (
            current_entity_relations()
            .filter(
                from_entity_id__in=entity_resolution_service.cluster_ids(
                    Entity.objects.get(pk=subject_id)
                ),
                relation_type="has-episode",
                to_entity__kind=Entity.Kind.EPISODE,
                to_entity__lifecycle=Entity.Lifecycle.ACTIVE,
            )
            .values("to_entity_id")
        )
        return Entity.objects.filter(pk__in=episode_ids).distinct().order_by("id")

    @staticmethod
    def get_finished_episode_ids(*, user_subject: UserSubject):
        if not user_subject:
            return []
        return list(
            UserEpisodeProgress.objects.filter(
                user_subject=user_subject,
                is_finished=True,
            )
            .order_by("episode_entity_id")
            .values_list("episode_entity_id", flat=True)
        )

    @classmethod
    def get_progress_summary(cls, *, user, subject_id):
        if not Entity.objects.filter(
            pk=subject_id,
            kind=Entity.Kind.WORK,
            lifecycle=Entity.Lifecycle.ACTIVE,
        ).exists():
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
            detail = entity_detail(episode, safe=True)
            facts = {fact["predicate"]: fact["value"] for fact in detail["facts"]}
            episodes.append(
                {
                    "id": str(episode.id),
                    "title": preferred_name(episode),
                    "type": facts.get("episode-type", ""),
                    "ep_num": facts.get("episode-number"),
                    "sort": facts.get("sort"),
                    "date": facts.get("air-date"),
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
