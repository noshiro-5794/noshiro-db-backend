from django.db.models import Q

from apps.community.models import CommunityBookmark


class CommunityBookmarkSelector:

    @staticmethod
    def list_my_bookmarks(*, user, target_type=None, keyword=None):
        qs = CommunityBookmark.objects.select_related(
            "post",
            "post__author",
            "post__author__profile",
            "post__subject",
            "review",
            "review__user_subject",
            "review__user_subject__user",
            "review__user_subject__user__profile",
            "review__user_subject__subject",
            "collection",
            "collection__user",
            "collection__user__profile",
        ).filter(user=user)

        if target_type:
            qs = qs.filter(**{f"{target_type}__isnull": False})

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(
                    Q(post__content__icontains=keyword)
                    | Q(post__subject__title__icontains=keyword)
                    | Q(post__subject__title_cn__icontains=keyword)
                    | Q(review__title__icontains=keyword)
                    | Q(review__content__icontains=keyword)
                    | Q(review__user_subject__subject__title__icontains=keyword)
                    | Q(review__user_subject__subject__title_cn__icontains=keyword)
                    | Q(collection__name__icontains=keyword)
                    | Q(collection__note__icontains=keyword)
                )

        return qs.order_by("-created_at", "-id")
