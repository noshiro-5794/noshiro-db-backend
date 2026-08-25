from django.urls import include, path

from apps.users.api.views.auth import (
    CodeLoginView,
    CookieTokenRefreshView,
    LogoutView,
    PasswordLoginView,
    RegisterView,
    ResetPasswordView,
    SendCodeView,
)
from apps.users.api.views.collections import (
    CollectionDetailView,
    CollectionItemDetailView,
    CollectionItemListCreateView,
    CollectionListCreateView,
)
from apps.users.api.views.library import (
    LibraryEntryDetailView,
    LibraryEntryEpisodeProgressItemView,
    LibraryEntryEpisodeProgressView,
    LibraryEntryListCreateView,
    LibraryEntryRatingDetailView,
    LibraryEntryReleaseView,
    LibraryEntryTagView,
    UserTagDetailView,
    UserTagListCreateView,
)
from apps.users.api.views.profiles import (
    MyAvatarUploadView,
    MyProfileStatsView,
    MyProfileView,
    MySettingsView,
    PublicUserDetailView,
    PublicUserLibraryView,
    PublicUserReviewListView,
)
from apps.users.api.views.public_collections import (
    PublicCollectionDetailView,
    PublicCollectionItemListView,
    PublicCollectionListView,
)
from apps.users.api.views.reviews import (
    LibraryEntryReviewListCreateView,
    MyReviewDetailView,
    MyReviewListView,
    PublicEntityReviewListView,
    PublicReviewDetailView,
)

auth_urlpatterns = [
    path("verification-codes/", SendCodeView.as_view(), name="auth-verification-code"),
    path("registrations/", RegisterView.as_view(), name="auth-registration"),
    path(
        "sessions/password/", PasswordLoginView.as_view(), name="auth-password-session"
    ),
    path("sessions/code/", CodeLoginView.as_view(), name="auth-code-session"),
    path("sessions/refresh/", CookieTokenRefreshView.as_view(), name="auth-refresh"),
    path("session/", LogoutView.as_view(), name="auth-session"),
    path("password-resets/", ResetPasswordView.as_view(), name="auth-password-reset"),
]

user_urlpatterns = [
    path("me/profile/", MyProfileView.as_view(), name="my-profile"),
    path("me/settings/", MySettingsView.as_view(), name="my-settings"),
    path("me/profile/stats/", MyProfileStatsView.as_view(), name="my-profile-stats"),
    path("me/avatar/", MyAvatarUploadView.as_view(), name="my-avatar"),
    path(
        "me/library/entries/",
        LibraryEntryListCreateView.as_view(),
        name="library-entry-list",
    ),
    path(
        "me/library/entries/<int:entry_id>/",
        LibraryEntryDetailView.as_view(),
        name="library-entry-detail",
    ),
    path(
        "me/library/entries/<int:entry_id>/releases/<uuid:release_id>/",
        LibraryEntryReleaseView.as_view(),
        name="library-entry-release",
    ),
    path(
        "me/library/entries/<int:entry_id>/tags/",
        LibraryEntryTagView.as_view(),
        name="library-entry-tags",
    ),
    path(
        "me/library/entries/<int:entry_id>/rating-details/",
        LibraryEntryRatingDetailView.as_view(),
        name="library-entry-rating-details",
    ),
    path(
        "me/library/entries/<int:entry_id>/episodes/progress/",
        LibraryEntryEpisodeProgressView.as_view(),
        name="library-entry-progress",
    ),
    path(
        "me/library/entries/<int:entry_id>/episodes/<uuid:episode_id>/progress/",
        LibraryEntryEpisodeProgressItemView.as_view(),
        name="library-entry-episode-progress",
    ),
    path(
        "me/library/entries/<int:entry_id>/reviews/",
        LibraryEntryReviewListCreateView.as_view(),
        name="library-entry-reviews",
    ),
    path("me/tags/", UserTagListCreateView.as_view(), name="tag-list"),
    path("me/tags/<int:tag_id>/", UserTagDetailView.as_view(), name="tag-detail"),
    path("me/reviews/", MyReviewListView.as_view(), name="my-review-list"),
    path(
        "me/reviews/<int:review_id>/",
        MyReviewDetailView.as_view(),
        name="my-review-detail",
    ),
    path("me/collections/", CollectionListCreateView.as_view(), name="collection-list"),
    path(
        "me/collections/<int:collection_id>/",
        CollectionDetailView.as_view(),
        name="collection-detail",
    ),
    path(
        "me/collections/<int:collection_id>/items/",
        CollectionItemListCreateView.as_view(),
        name="collection-item-list",
    ),
    path(
        "me/collections/<int:collection_id>/items/<int:item_id>/",
        CollectionItemDetailView.as_view(),
        name="collection-item-detail",
    ),
    path("<int:user_id>/", PublicUserDetailView.as_view(), name="public-user"),
    path(
        "<int:user_id>/library/entries/",
        PublicUserLibraryView.as_view(),
        name="public-user-library",
    ),
    path(
        "<int:user_id>/reviews/",
        PublicUserReviewListView.as_view(),
        name="public-user-reviews",
    ),
    path(
        "<int:user_id>/collections/",
        PublicCollectionListView.as_view(),
        name="public-user-collections",
    ),
    path(
        "<int:user_id>/collections/<int:collection_id>/",
        PublicCollectionDetailView.as_view(),
        name="public-user-collection",
    ),
    path(
        "<int:user_id>/collections/<int:collection_id>/items/",
        PublicCollectionItemListView.as_view(),
        name="public-user-collection-items",
    ),
    path(
        "entities/<uuid:entity_id>/reviews/",
        PublicEntityReviewListView.as_view(),
        name="public-entity-reviews",
    ),
    path(
        "reviews/<int:review_id>/",
        PublicReviewDetailView.as_view(),
        name="public-review-detail",
    ),
]

urlpatterns = [
    path("auth/", include(auth_urlpatterns)),
    path("users/", include(user_urlpatterns)),
]
