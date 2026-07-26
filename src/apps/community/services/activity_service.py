from decimal import Decimal

from django.db import transaction

from apps.community.models import Activity, FeedPolicy, Visibility


class ActivityService:
    @staticmethod
    def _metadata_value(value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                key: ActivityService._metadata_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [ActivityService._metadata_value(item) for item in value]
        return str(value)

    @staticmethod
    def _visibility_from_public_flag(is_public: bool) -> str:
        return Visibility.PUBLIC if is_public else Visibility.PRIVATE

    @staticmethod
    def _subject_snapshot_from_user_subject(user_subject):
        if not user_subject:
            return {}

        subject = user_subject.subject

        return ActivityService._metadata_value(
            {
                "subject": {
                    "id": str(subject.id),
                    "subject_type": subject.subject_type,
                    "title": subject.title,
                    "title_cn": subject.title_cn,
                    "date": subject.date,
                    "image_thumbnail": subject.image_thumbnail,
                    "platform": subject.platform,
                    "nsfw": subject.nsfw,
                },
                "user_subject": {
                    "id": user_subject.id,
                    "status": user_subject.status,
                    "simple_rating": user_subject.simple_rating,
                    "rating": user_subject.rating,
                    "comment": user_subject.comment,
                    "is_public": user_subject.is_public,
                },
            }
        )

    @staticmethod
    @transaction.atomic
    def create_user_subject_created_activity(*, user, user_subject):
        subject = user_subject.subject

        return Activity.objects.create(
            user=user,
            subject=subject,
            activity_type=Activity.ActivityType.USER_SUBJECT_CREATED,
            user_subject=user_subject,
            message=f"Added '{subject.title}' to collection",
            visibility=ActivityService._visibility_from_public_flag(
                user_subject.is_public
            ),
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"user_subject:{user.id}:{subject.id}",
            dedupe_key=f"user_subject_created:{user_subject.id}",
            metadata=ActivityService._subject_snapshot_from_user_subject(user_subject),
        )

    @staticmethod
    @transaction.atomic
    def create_user_subject_updated_activity(*, user, user_subject):
        subject = user_subject.subject

        return Activity.objects.create(
            user=user,
            subject=subject,
            activity_type=Activity.ActivityType.USER_SUBJECT_UPDATED,
            user_subject=user_subject,
            message=f"Updated collection status for '{subject.title}'",
            visibility=ActivityService._visibility_from_public_flag(
                user_subject.is_public
            ),
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"user_subject:{user.id}:{subject.id}",
            metadata=ActivityService._subject_snapshot_from_user_subject(user_subject),
        )

    @staticmethod
    @transaction.atomic
    def create_review_created_activity(*, user, review):
        user_subject = review.user_subject
        subject = user_subject.subject
        is_public = user_subject.is_public and review.is_public

        return Activity.objects.create(
            user=user,
            subject=subject,
            activity_type=Activity.ActivityType.REVIEW_CREATED,
            user_subject=user_subject,
            review=review,
            message=f"Posted a review for '{subject.title}': {review.title}",
            visibility=ActivityService._visibility_from_public_flag(is_public),
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"review:{subject.id}",
            dedupe_key=f"review_created:{review.id}",
            metadata={
                **ActivityService._subject_snapshot_from_user_subject(user_subject),
                "review": {
                    "id": review.id,
                    "title": review.title,
                },
            },
        )

    @staticmethod
    @transaction.atomic
    def create_collection_created_activity(*, user, collection):
        return Activity.objects.create(
            user=user,
            activity_type=Activity.ActivityType.COLLECTION_CREATED,
            collection=collection,
            message=f"Created collection '{collection.name}'",
            visibility=ActivityService._visibility_from_public_flag(
                collection.is_public
            ),
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"collection:{user.id}",
            dedupe_key=f"collection_created:{collection.id}",
            metadata={
                "collection": {
                    "id": collection.id,
                    "name": collection.name,
                    "simple_rating": collection.simple_rating,
                    "note": collection.note,
                }
            },
        )

    @staticmethod
    @transaction.atomic
    def create_collection_item_added_activity(*, user, collection_item):
        collection = collection_item.collection
        user_subject = collection_item.user_subject
        subject = user_subject.subject
        is_public = user_subject.is_public and collection.is_public

        return Activity.objects.create(
            user=user,
            subject=subject,
            activity_type=Activity.ActivityType.COLLECTION_ITEM_ADDED,
            user_subject=user_subject,
            collection=collection,
            collection_item=collection_item,
            message=f"Added '{subject.title}' to collection '{collection.name}'",
            visibility=ActivityService._visibility_from_public_flag(is_public),
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"collection:{collection.id}",
            dedupe_key=f"collection_item_added:{collection_item.id}",
            metadata={
                **ActivityService._subject_snapshot_from_user_subject(user_subject),
                "collection": {
                    "id": collection.id,
                    "name": collection.name,
                },
                "collection_item": {
                    "id": collection_item.id,
                    "relation": collection_item.relation,
                    "order": collection_item.order,
                },
            },
        )

    @staticmethod
    @transaction.atomic
    def create_user_followed_activity(*, follower, following):
        profile = getattr(following, "profile", None)
        nickname = ""
        avatar = ""

        if profile:
            nickname = getattr(profile, "nickname", "") or ""
            profile_avatar = getattr(profile, "avatar", "")
            if profile_avatar:
                avatar = (
                    profile_avatar.url
                    if hasattr(profile_avatar, "url")
                    else str(profile_avatar)
                )

        activity, _ = Activity.objects.update_or_create(
            dedupe_key=f"user_followed:{follower.id}:{following.id}",
            defaults={
                "user": follower,
                "activity_type": Activity.ActivityType.USER_FOLLOWED,
                "target_user": following,
                "message": "Followed a user",
                "visibility": Visibility.PUBLIC,
                "feed_policy": FeedPolicy.NORMAL,
                "group_key": f"follow:{follower.id}",
                "metadata": {
                    "target_user": {
                        "id": following.id,
                        "nickname": nickname,
                        "avatar": avatar,
                    }
                },
            },
        )
        return activity

    @staticmethod
    @transaction.atomic
    def create_comment_created_activity(*, user, comment):
        post = comment.post
        subject = post.subject if post else None

        return Activity.objects.create(
            user=user,
            subject=subject,
            post=post,
            comment=comment,
            activity_type=Activity.ActivityType.COMMENT_CREATED,
            message="Posted a comment",
            visibility=comment.visibility,
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"comment:{post.id if post else 'unknown'}",
            dedupe_key=f"comment_created:{comment.id}",
            metadata={
                "comment": {
                    "id": comment.id,
                    "post_id": post.id if post else None,
                }
            },
        )
