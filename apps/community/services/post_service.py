from django.db import transaction
from django.utils import timezone

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
