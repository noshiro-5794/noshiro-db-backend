from django.db import transaction
from django.utils import timezone

from apps.community.exceptions import (
    CommunityPermissionDenied,
    CommunityPostNotFound,
    CommunityTargetLocked,
)
from apps.community.models import Activity, CommunityPost, FeedPolicy, Visibility


class CommunityPostService:

    @staticmethod
    @transaction.atomic
    def create_post(
        *,
        author,
        content: str,
        subject=None,
        visibility=Visibility.PUBLIC,
        is_spoiler=False,
        is_nsfw=False,
    ) -> CommunityPost:
        now = timezone.now()
        post = CommunityPost.objects.create(
            author=author,
            subject=subject,
            post_type=(
                CommunityPost.PostType.SUBJECT
                if subject
                else CommunityPost.PostType.STATUS
            ),
            content=content,
            visibility=visibility,
            feed_policy=FeedPolicy.NORMAL,
            is_spoiler=is_spoiler,
            is_nsfw=is_nsfw,
            last_activity_at=now,
        )
        Activity.objects.create(
            user=author,
            subject=subject,
            post=post,
            activity_type=Activity.ActivityType.POST_CREATED,
            message="Posted a status",
            visibility=visibility,
            feed_policy=FeedPolicy.NORMAL,
            group_key=f"post:{author.id}",
            dedupe_key=f"post_created:{post.id}",
            metadata={
                "post": {
                    "id": post.id,
                    "subject_id": str(subject.id) if subject else None,
                }
            },
        )
        return post

    @staticmethod
    def _get_my_post_or_raise(*, author, post_id: int):
        post = CommunityPost.objects.filter(id=post_id).first()
        if not post:
            raise CommunityPostNotFound()
        if post.author_id != author.id:
            raise CommunityPermissionDenied()
        return post

    @staticmethod
    @transaction.atomic
    def update_post(*, author, post_id: int, **fields):
        post = CommunityPostService._get_my_post_or_raise(
            author=author,
            post_id=post_id,
        )
        if post.is_locked or post.feed_policy == FeedPolicy.HIDDEN:
            raise CommunityTargetLocked()

        allowed_fields = {
            "content",
            "visibility",
            "is_spoiler",
            "is_nsfw",
        }
        update_fields = []
        for key, value in fields.items():
            if key not in allowed_fields:
                continue
            setattr(post, key, value)
            update_fields.append(key)

        if update_fields:
            update_fields.append("updated_at")
            post.save(update_fields=update_fields)

        return post

    @staticmethod
    @transaction.atomic
    def delete_post(*, author, post_id: int):
        post = CommunityPostService._get_my_post_or_raise(
            author=author,
            post_id=post_id,
        )
        if post.is_locked or post.feed_policy == FeedPolicy.HIDDEN:
            raise CommunityTargetLocked()
        post.delete()

    @staticmethod
    @transaction.atomic
    def hide_post(*, post):
        post.feed_policy = FeedPolicy.HIDDEN
        post.save(update_fields=["feed_policy", "updated_at"])
        Activity.objects.filter(post=post).update(feed_policy=FeedPolicy.HIDDEN)
        return post

    @staticmethod
    @transaction.atomic
    def lock_post(*, post):
        post.is_locked = True
        post.save(update_fields=["is_locked", "updated_at"])
        return post
