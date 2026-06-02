from django.db import transaction

from apps.users.models import Review
from apps.users.selectors.library.review_selector import ReviewSelector
from apps.community.services.activity_service import ActivityService


class ReviewService:

    @staticmethod
    @transaction.atomic
    def create_review(
        *,
        user,
        user_subject_id: int,
        title: str,
        content: str,
        is_public: bool = True,
        is_spoiler: bool = False,
    ):
        user_subject = ReviewSelector.get_my_subject_or_raise(
            user=user,
            user_subject_id=user_subject_id,
        )

        return ReviewService.create_user_subject_review(
            user_subject=user_subject,
            title=title,
            content=content,
            is_public=is_public,
            is_spoiler=is_spoiler,
        )

    @staticmethod
    @transaction.atomic
    def create_review_by_subject_id(
        *,
        user,
        subject_id,
        title: str,
        content: str,
        is_public: bool = True,
        is_spoiler: bool = False,
    ):
        user_subject = ReviewSelector.get_my_subject_by_subject_id_or_raise(
            user=user,
            subject_id=subject_id,
        )

        return ReviewService.create_user_subject_review(
            user_subject=user_subject,
            title=title,
            content=content,
            is_public=is_public,
            is_spoiler=is_spoiler,
        )

    @staticmethod
    def create_user_subject_review(
        *,
        user_subject,
        title: str,
        content: str,
        is_public: bool,
        is_spoiler: bool,
    ):

        review = Review.objects.create(
            user_subject=user_subject,
            title=title.strip(),
            content=content,
            is_public=is_public,
            is_spoiler=is_spoiler,
        )

        ActivityService.create_review_created_activity(
            user=user_subject.user,
            review=review,
        )

        return review

    @staticmethod
    @transaction.atomic
    def update_review(
        *,
        user,
        review_id: int,
        **fields,
    ):
        review = ReviewSelector.get_my_review_or_raise(
            user=user,
            review_id=review_id,
        )

        allowed_fields = {
            "title",
            "content",
            "is_public",
            "is_spoiler",
        }

        update_fields = []

        for key, value in fields.items():
            if key not in allowed_fields:
                continue

            if key == "title":
                value = value.strip()

            setattr(review, key, value)
            update_fields.append(key)

        if update_fields:
            update_fields.append("updated_at")
            review.save(update_fields=update_fields)

        return review

    @staticmethod
    @transaction.atomic
    def delete_review(*, user, review_id: int):
        review = ReviewSelector.get_my_review_or_raise(
            user=user,
            review_id=review_id,
        )

        review.delete()
