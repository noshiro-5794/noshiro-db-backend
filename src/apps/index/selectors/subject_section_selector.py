from django.db.models import Case, IntegerField, Prefetch, Q, Value, When

from apps.index.exceptions import EpisodeNotFound
from apps.index.models import (
    Episode,
    SubjectCharacterActorRelation,
    SubjectSubjectRelation,
)
from apps.index.selectors.subject_selector import SubjectSelector


class SubjectSectionSelector:
    @classmethod
    def list_subject_episodes(cls, *, subject_id, type=None):
        subject = SubjectSelector.get_subject_reference_or_raise(subject_id=subject_id)

        qs = subject.episodes.all()
        if type:
            qs = qs.filter(type=type)
        return qs.order_by("sort", "ep_num", "id")

    @classmethod
    def get_subject_episode_or_raise(cls, *, subject_id, episode_id):
        try:
            return Episode.objects.get(subject_id=subject_id, id=episode_id)
        except Episode.DoesNotExist as exc:
            raise EpisodeNotFound() from exc

    @classmethod
    def list_subject_staff(cls, *, subject_id, role=None):
        subject = SubjectSelector.get_subject_reference_or_raise(subject_id=subject_id)

        qs = (
            subject.staff_relations.select_related("staff")
            .annotate(
                role_priority=Case(
                    When(role__icontains="監督", then=Value(0)),
                    When(role__icontains="导演", then=Value(0)),
                    When(role__icontains="director", then=Value(0)),
                    When(role__icontains="原作", then=Value(1)),
                    When(role__icontains="脚本", then=Value(2)),
                    When(role__icontains="系列构成", then=Value(2)),
                    When(role__icontains="シリーズ構成", then=Value(2)),
                    When(role__icontains="音乐", then=Value(3)),
                    When(role__icontains="音楽", then=Value(3)),
                    default=Value(50),
                    output_field=IntegerField(),
                )
            )
            .order_by("role_priority", "role", "staff__name", "id")
        )

        if role:
            qs = qs.filter(role=role)

        return qs

    @classmethod
    def list_subject_staff_roles(cls, *, subject_id):
        subject = SubjectSelector.get_subject_reference_or_raise(subject_id=subject_id)

        return (
            subject.staff_relations.exclude(role="")
            .values_list("role", flat=True)
            .distinct()
            .order_by("role")
        )

    @classmethod
    def list_subject_characters(cls, *, subject_id):
        subject = SubjectSelector.get_subject_reference_or_raise(subject_id=subject_id)

        return (
            subject.character_relations.select_related("character")
            .prefetch_related(
                Prefetch(
                    "character__actor_relations",
                    queryset=SubjectCharacterActorRelation.objects.filter(
                        subject_id=subject_id
                    )
                    .select_related("actor")
                    .order_by("actor__name", "id"),
                    to_attr="subject_actor_relations",
                )
            )
            .annotate(
                role_priority=Case(
                    When(role__icontains="主人公", then=Value(0)),
                    When(role__icontains="主角", then=Value(0)),
                    When(role__icontains="main", then=Value(0)),
                    When(role__icontains="主要", then=Value(1)),
                    When(role__icontains="support", then=Value(2)),
                    default=Value(50),
                    output_field=IntegerField(),
                )
            )
            .order_by("role_priority", "role", "character__name", "id")
        )

    @classmethod
    def list_subject_relations(cls, *, subject_id):
        SubjectSelector.get_subject_reference_or_raise(subject_id=subject_id)

        return (
            SubjectSubjectRelation.objects.select_related("source", "target")
            .filter(Q(source_id=subject_id) | Q(target_id=subject_id))
            .order_by("relation", "id")
        )
