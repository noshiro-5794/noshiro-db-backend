from apps.community.models import CommunityBookmark


class CommunityBookmarkSelector:

    @staticmethod
    def list_my_bookmarks(*, user, target_type=None):
        qs = CommunityBookmark.objects.select_related(
            "post",
            "review",
            "collection",
        ).filter(user=user)

        if target_type:
            qs = qs.filter(**{f"{target_type}__isnull": False})

        return qs.order_by("-created_at", "-id")
