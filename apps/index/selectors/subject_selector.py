from django.db.models import (
    Count,
    Exists,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, Greatest
from django.contrib.postgres.search import TrigramSimilarity

from apps.index.constants import PRIMARY_SUBJECT_TYPES
from apps.index.exceptions import SubjectNotFound
from apps.index.models import (
    Episode,
    Subject,
    SubjectCharacterRelation,
    SubjectStaffRelation,
    SubjectSubjectRelation,
)


class SubjectSelector:

    @staticmethod
    def base_queryset():
        return Subject.objects.all()

    @staticmethod
    def with_section_counts(qs):
        return qs.annotate(
            episode_count=Coalesce(
                Subquery(
                    Episode.objects.filter(subject_id=OuterRef("pk"))
                    .order_by()
                    .values("subject_id")
                    .annotate(count=Count("id"))
                    .values("count")[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            ),
            staff_count=Coalesce(
                Subquery(
                    SubjectStaffRelation.objects.filter(subject_id=OuterRef("pk"))
                    .order_by()
                    .values("subject_id")
                    .annotate(count=Count("id"))
                    .values("count")[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            ),
            character_count=Coalesce(
                Subquery(
                    SubjectCharacterRelation.objects.filter(subject_id=OuterRef("pk"))
                    .order_by()
                    .values("subject_id")
                    .annotate(count=Count("id"))
                    .values("count")[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            ),
        )

    @staticmethod
    def with_subject_relations(qs):
        outgoing_relations = SubjectSubjectRelation.objects.filter(
            source_id=OuterRef("pk")
        )
        incoming_relations = SubjectSubjectRelation.objects.filter(
            target_id=OuterRef("pk")
        )

        return qs.annotate(
            has_outgoing_relation=Exists(outgoing_relations),
            has_incoming_relation=Exists(incoming_relations),
        ).filter(
            Q(has_outgoing_relation=True) | Q(has_incoming_relation=True),
        )

    @classmethod
    def list_subjects(
        cls,
        *,
        keyword=None,
        subject_type=None,
        nsfw=None,
        year=None,
        season=None,
        platform=None,
        source_id=None,
        date_from=None,
        date_to=None,
        episodes_min=None,
        episodes_max=None,
        ordering="-updated_at",
    ):
        qs = cls.base_queryset().filter(subject_type__in=PRIMARY_SUBJECT_TYPES)
        qs = cls.with_subject_relations(qs)

        if subject_type:
            qs = qs.filter(subject_type=subject_type)

        if nsfw is not None:
            qs = qs.filter(nsfw=nsfw)

        if year:
            qs = qs.filter(date__year=year)

        if season:
            qs = cls.filter_by_season(qs, season=season)

        if platform:
            platform = platform.strip()
            if platform:
                qs = qs.filter(platform__icontains=platform)

        if source_id:
            source_id = source_id.strip()
            if source_id:
                qs = qs.filter(id_source=source_id)

        if date_from:
            qs = qs.filter(date__gte=date_from)

        if date_to:
            qs = qs.filter(date__lte=date_to)

        if episodes_min is not None or episodes_max is not None:
            qs = cls.filter_by_episode_count(
                qs,
                minimum=episodes_min,
                maximum=episodes_max,
            )

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = cls.apply_keyword_search(qs, keyword=keyword)
                return qs.order_by("-search_score", "-updated_at", "-id")

        allowed_ordering = {
            "date",
            "-date",
            "title",
            "-title",
            "updated_at",
            "-updated_at",
            "created_at",
            "-created_at",
        }

        if ordering not in allowed_ordering:
            ordering = "-updated_at"

        return qs.order_by(ordering, "-id")

    @staticmethod
    def apply_keyword_search(qs, *, keyword: str):
        zero = Value(0.0, output_field=FloatField())

        qs = qs.annotate(
            title_similarity=Coalesce(TrigramSimilarity("title", keyword), zero),
            title_cn_similarity=Coalesce(
                TrigramSimilarity("title_cn", keyword),
                zero,
            ),
        ).annotate(
            search_score=Greatest("title_similarity", "title_cn_similarity")
        )

        return qs.filter(
            Q(title__icontains=keyword)
            | Q(title_cn__icontains=keyword)
            | Q(search_score__gte=0.15)
        )

    @staticmethod
    def filter_by_season(qs, *, season: str):
        season_months = {
            "winter": [1, 2, 3],
            "spring": [4, 5, 6],
            "summer": [7, 8, 9],
            "fall": [10, 11, 12],
        }
        months = season_months.get(season)
        return qs.filter(date__month__in=months) if months else qs

    @staticmethod
    def filter_by_episode_count(qs, *, minimum=None, maximum=None):
        if minimum is not None:
            qs = qs.filter(
                Q(total_episodes__gte=minimum)
                | Q(total_episodes__isnull=True, eps__gte=minimum)
            )

        if maximum is not None:
            qs = qs.filter(
                Q(total_episodes__lte=maximum)
                | Q(total_episodes__isnull=True, eps__lte=maximum)
            )

        return qs

    @classmethod
    def get_subject_or_raise(cls, *, subject_id):
        try:
            return cls.with_section_counts(cls.base_queryset()).get(id=subject_id)
        except Subject.DoesNotExist:
            raise SubjectNotFound()

    @staticmethod
    def get_subject_reference_or_raise(*, subject_id):
        try:
            return Subject.objects.only("id").get(id=subject_id)
        except Subject.DoesNotExist:
            raise SubjectNotFound()
