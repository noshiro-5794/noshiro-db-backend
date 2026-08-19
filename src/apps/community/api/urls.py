from django.urls import path

from apps.community.api.views.activities import (
    MyActivityListView,
    MyFeedView,
    PublicActivityListView,
    PublicUserActivityListView,
)
from apps.community.api.views.comments import (
    CommunityCommentDetailView,
    CommunityCommentListCreateView,
    StaffCommunityCommentModerationView,
)
from apps.community.api.views.follows import (
    MyFollowerListView,
    MyFollowingListView,
    UserFollowerListView,
    UserFollowingListView,
)
from apps.community.api.views.interactions import (
    BookmarkListView,
    BookmarkView,
    ReactionView,
)
from apps.community.api.views.notifications import (
    MyNotificationListView,
    MyNotificationReadAllView,
    MyNotificationReadView,
    MyNotificationUnreadCountView,
)
from apps.community.api.views.posts import (
    CommunityPostCommentListCreateView,
    CommunityPostDetailView,
    CommunityPostListCreateView,
    StaffCommunityPostModerationView,
)
from apps.community.api.views.relationship_actions import (
    BlockView,
    FollowView,
    MuteView,
)
from apps.community.api.views.relationships import MyBlockListView, MyMuteListView
from apps.community.api.views.reports import (
    CommunityReportCreateView,
    MyCommunityReportListView,
    StaffCommunityReportListView,
    StaffCommunityReportResolveView,
)

urlpatterns = [
    path("community/posts/", CommunityPostListCreateView.as_view(), name="post-list"),
    path(
        "community/posts/<int:post_id>/",
        CommunityPostDetailView.as_view(),
        name="post-detail",
    ),
    path(
        "community/posts/<int:post_id>/comments/",
        CommunityPostCommentListCreateView.as_view(),
        name="post-comment-list",
    ),
    path(
        "community/comments/",
        CommunityCommentListCreateView.as_view(),
        name="comment-list",
    ),
    path(
        "community/comments/<int:comment_id>/",
        CommunityCommentDetailView.as_view(),
        name="comment-detail",
    ),
    path(
        "community/activities/", PublicActivityListView.as_view(), name="activity-list"
    ),
    path(
        "community/me/activities/",
        MyActivityListView.as_view(),
        name="my-activity-list",
    ),
    path("community/me/feed/", MyFeedView.as_view(), name="my-feed"),
    path(
        "community/users/<int:user_id>/activities/",
        PublicUserActivityListView.as_view(),
        name="user-activity-list",
    ),
    path("community/me/following/", MyFollowingListView.as_view(), name="my-following"),
    path("community/me/followers/", MyFollowerListView.as_view(), name="my-followers"),
    path(
        "community/me/following/<int:target_user_id>/",
        FollowView.as_view(),
        name="follow-relation",
    ),
    path("community/me/blocks/", MyBlockListView.as_view(), name="my-blocks"),
    path(
        "community/me/blocks/<int:target_user_id>/",
        BlockView.as_view(),
        name="block-relation",
    ),
    path("community/me/mutes/", MyMuteListView.as_view(), name="my-mutes"),
    path(
        "community/me/mutes/<int:target_user_id>/",
        MuteView.as_view(),
        name="mute-relation",
    ),
    path(
        "community/users/<int:user_id>/following/",
        UserFollowingListView.as_view(),
        name="user-following",
    ),
    path(
        "community/users/<int:user_id>/followers/",
        UserFollowerListView.as_view(),
        name="user-followers",
    ),
    path("community/me/bookmarks/", BookmarkListView.as_view(), name="bookmark-list"),
    path(
        "community/me/bookmarks/<str:target_type>/<int:target_id>/",
        BookmarkView.as_view(),
        name="bookmark",
    ),
    path(
        "community/me/reactions/<str:target_type>/<int:target_id>/<str:reaction_type>/",
        ReactionView.as_view(),
        name="reaction",
    ),
    path(
        "community/me/notifications/",
        MyNotificationListView.as_view(),
        name="notification-list",
    ),
    path(
        "community/me/notifications/unread-count/",
        MyNotificationUnreadCountView.as_view(),
        name="notification-unread-count",
    ),
    path(
        "community/me/notifications/read-state/",
        MyNotificationReadAllView.as_view(),
        name="notification-read-state",
    ),
    path(
        "community/me/notifications/<int:notification_id>/read-state/",
        MyNotificationReadView.as_view(),
        name="notification-item-read-state",
    ),
    path("community/reports/", CommunityReportCreateView.as_view(), name="report-list"),
    path(
        "community/me/reports/",
        MyCommunityReportListView.as_view(),
        name="my-report-list",
    ),
    path(
        "community/moderation/reports/",
        StaffCommunityReportListView.as_view(),
        name="moderation-report-list",
    ),
    path(
        "community/moderation/reports/<int:report_id>/",
        StaffCommunityReportResolveView.as_view(),
        name="moderation-report-detail",
    ),
    path(
        "community/moderation/posts/<int:post_id>/",
        StaffCommunityPostModerationView.as_view(),
        name="moderation-post-detail",
    ),
    path(
        "community/moderation/comments/<int:comment_id>/",
        StaffCommunityCommentModerationView.as_view(),
        name="moderation-comment-detail",
    ),
]
