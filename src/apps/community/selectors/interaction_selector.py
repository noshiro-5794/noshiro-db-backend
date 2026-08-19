from django.db.models import Q

from apps.community.models import CommunityBookmark


class CommunityBookmarkSelector:
    @staticmethod
    def list_my_bookmarks(*, user, target_type=None, keyword=None):
        qs = (
            CommunityBookmark.objects.select_related(
                "post",
                "post__author",
                "post__author__profile",
                "post__entity",
                "post__entity__work",
                "review",
                "review__user_subject",
                "review__user_subject__user",
                "review__user_subject__user__profile",
                "review__user_subject__entity",
                "review__user_subject__entity__work",
                "collection",
                "collection__user",
                "collection__user__profile",
            )
            .prefetch_related(
                "post__entity__names",
                "post__entity__media__asset",
                "post__entity__index_memberships__collection",
                "review__user_subject__entity__names",
                "review__user_subject__entity__media__asset",
                "review__user_subject__entity__index_memberships__collection",
            )
            .filter(user=user)
        )

        if target_type:
            qs = qs.filter(**{f"{target_type}__isnull": False})

        if keyword:
            keyword = keyword.strip()
            if keyword:
                qs = qs.filter(
                    Q(post__content__icontains=keyword)
                    | Q(post__entity__names__text__icontains=keyword)
                    | Q(review__title__icontains=keyword)
                    | Q(review__content__icontains=keyword)
                    | Q(review__user_subject__entity__names__text__icontains=keyword)
                    | Q(collection__name__icontains=keyword)
                    | Q(collection__note__icontains=keyword)
                )

        return qs.distinct().order_by("-created_at", "-id")
