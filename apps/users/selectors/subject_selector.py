from django.db.models import Q, Value, FloatField
from django.db.models.functions import Coalesce, Greatest
from django.contrib.postgres.search import TrigramSimilarity

from apps.index.constants import PRIMARY_SUBJECT_TYPES
from apps.users.models import (
    Review,
    UserEpisodeProgress,
    UserSubject,
    UserSubjectRatingDetail,
    UserTag,
)
from apps.users.exceptions import UserSubjectNotFound


class SubjectSelector:

    @staticmethod
    def base_queryset():
        return UserSubject.objects.select_related("user", "subject").prefetch_related(
            "tag_relations__tag", "rating_details"
        )

    @classmethod
    def get_user_subject(cls, *, user, user_subject_id: int) -> UserSubject:
        return cls.base_queryset().get(
            id=user_subject_id,
            user=user,
            subject__subject_type__in=PRIMARY_SUBJECT_TYPES,
        )

    @classmethod
    def get_user_subject_or_raise(cls, *, user, user_subject_id: int) -> UserSubject:
        try:
            return cls.get_user_subject(
                user=user,
                user_subject_id=user_subject_id,
            )
        except UserSubject.DoesNotExist:
            raise UserSubjectNotFound()

    @classmethod
    def list_my_subjects(
        cls,
        *,
        user,
        status=None,
        subject_type=None,
        keyword=None,
        tag_id=None,
        ordering="-created_at",
    ):
        qs = cls.base_queryset().filter(
            user=user,
            subject__subject_type__in=PRIMARY_SUBJECT_TYPES,
        )
        if status:
            qs = qs.filter(status=status)
        if subject_type:
            qs = qs.filter(subject__subject_type=subject_type)
        if tag_id:
            qs = qs.filter(tag_relations__tag_id=tag_id).distinct()
        if keyword:
            qs = cls.apply_keyword_search(qs, keyword=keyword)
            return qs.order_by("-search_score", "-created_at", "-id")

        allowed_ordering = {
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
            "simple_rating",
            "-simple_rating",
            "rating",
            "-rating",
            "watch_start_date",
            "-watch_start_date",
            "watch_end_date",
            "-watch_end_date",
        }
        if ordering not in allowed_ordering:
            ordering = "-created_at"
        return qs.order_by(ordering, "-id")

    @staticmethod
    def apply_keyword_search(qs, *, keyword: str):
        keyword = keyword.strip()
        if not keyword:
            return qs

        zero = Value(0.0, output_field=FloatField())
        qs = qs.annotate(
            title_similarity=Coalesce(
                TrigramSimilarity("subject__title", keyword), zero
            ),
            title_cn_similarity=Coalesce(
                TrigramSimilarity("subject__title_cn", keyword), zero
            ),
        ).annotate(search_score=Greatest("title_similarity", "title_cn_similarity"))

        return qs.filter(
            Q(subject__title__icontains=keyword)
            | Q(subject__title_cn__icontains=keyword)
            | Q(search_score__gte=0.15)
        )

    @classmethod
    def get_my_subject_context(cls, *, user, subject_id):
        user_subject = (
            cls.base_queryset()
            .filter(
                user=user,
                subject_id=subject_id,
                subject__subject_type__in=PRIMARY_SUBJECT_TYPES,
            )
            .first()
        )

        if not user_subject:
            return {
                "is_marked": False,
                "user_subject": None,
                "tags": [],
                "rating_details": [],
                "reviews": [],
                "finished_episode_ids": [],
                "finished_count": 0,
            }

        tags = UserTag.objects.filter(
            subject_relations__user_subject=user_subject,
        ).order_by("name", "id")

        rating_details = UserSubjectRatingDetail.objects.filter(
            user_subject=user_subject,
        ).order_by("id")

        reviews = Review.objects.filter(
            user_subject=user_subject,
        ).order_by("-created_at", "-id")

        finished_episode_ids = list(
            UserEpisodeProgress.objects.filter(
                user_subject=user_subject,
                is_finished=True,
            )
            .order_by("episode__sort", "episode__ep_num", "episode_id")
            .values_list("episode_id", flat=True)
        )

        return {
            "is_marked": True,
            "user_subject": user_subject,
            "tags": tags,
            "rating_details": rating_details,
            "reviews": reviews,
            "finished_episode_ids": finished_episode_ids,
            "finished_count": len(finished_episode_ids),
        }
