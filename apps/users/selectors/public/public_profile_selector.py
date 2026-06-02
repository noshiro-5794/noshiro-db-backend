from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from apps.users.models import (
    UserSubject,
    Review,
    Collection,
)
from apps.community.models import UserFollow
from apps.users.exceptions import UserNotFound

User = get_user_model()


class PublicProfileSelector:

    @staticmethod
    def get_user_by_id(*, user_id: int):
        return User.objects.select_related("profile").filter(id=user_id).first()

    @classmethod
    def get_user_by_id_or_raise(cls, *, user_id: int):
        user = cls.get_user_by_id(user_id=user_id)

        if not user:
            raise UserNotFound()

        return user

    @classmethod
    def get_public_profile(cls, *, target_user_id: int, viewer=None):
        user_qs = (
            User.objects.select_related("profile")
            .filter(id=target_user_id)
            .annotate(
                public_subject_count=Count(
                    "subjects",
                    filter=Q(subjects__is_public=True),
                    distinct=True,
                ),
                collection_count=Count(
                    "collections",
                    filter=Q(collections__is_public=True),
                    distinct=True,
                ),
                following_count=Count(
                    "following_relations",
                    distinct=True,
                ),
                follower_count=Count(
                    "follower_relations",
                    distinct=True,
                ),
            )
        )

        user = user_qs.first()

        if not user:
            raise UserNotFound()

        review_qs = Review.objects.filter(
            user_subject__user=user,
            user_subject__is_public=True,
        )

        review_qs = review_qs.filter(is_public=True)

        user.public_review_count = review_qs.count()

        if viewer and viewer.is_authenticated:
            user.is_following = UserFollow.objects.filter(
                follower=viewer,
                following=user,
            ).exists()
        else:
            user.is_following = False

        return user

    @staticmethod
    def list_public_user_subjects(
        *,
        user,
        status=None,
        subject_type=None,
        keyword=None,
        ordering="-id",
    ):
        qs = UserSubject.objects.select_related("user", "subject").filter(
            user=user,
            is_public=True,
        )

        if status:
            qs = qs.filter(status=status)

        if subject_type:
            qs = qs.filter(subject__subject_type=subject_type)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(
                    Q(subject__title__icontains=keyword)
                    | Q(subject__title_cn__icontains=keyword)
                    | Q(comment__icontains=keyword)
                )

        allowed_ordering = {
            "id",
            "-id",
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
            ordering = "-id"

        return qs.order_by(ordering, "-id")

    @staticmethod
    def list_public_reviews(
        *,
        user,
        keyword=None,
        ordering="-id",
    ):
        qs = Review.objects.select_related(
            "user_subject",
            "user_subject__user",
            "user_subject__subject",
        ).filter(
            user_subject__user=user,
            user_subject__is_public=True,
        )

        qs = qs.filter(is_public=True)

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(
                    Q(title__icontains=keyword) | Q(content__icontains=keyword)
                )

        allowed_ordering = {
            "id",
            "-id",
        }

        if hasattr(Review, "created_at"):
            allowed_ordering.update(
                {
                    "created_at",
                    "-created_at",
                }
            )

        if ordering not in allowed_ordering:
            ordering = "-id"

        return qs.order_by(ordering, "-id")

    @staticmethod
    def list_public_collections(
        *,
        user,
        keyword=None,
        ordering="-id",
    ):
        qs = Collection.objects.filter(
            user=user,
            is_public=True,
        ).annotate(
            item_count=Count("items", distinct=True)
        )

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(Q(name__icontains=keyword) | Q(note__icontains=keyword))

        allowed_ordering = {
            "id",
            "-id",
            "name",
            "-name",
            "simple_rating",
            "-simple_rating",
            "item_count",
            "-item_count",
        }

        if ordering not in allowed_ordering:
            ordering = "-id"

        return qs.order_by(ordering, "-id")
