from django.urls import path

from apps.sync.api.views.manual_sync_view import (
    BangumiSubjectSyncView,
    CalendarSyncRunView,
    IncrementalSyncRunView,
    IncrementalSyncStatusView,
    SubjectResyncView,
)


urlpatterns = [
    path(
        "subjects/bangumi/",
        BangumiSubjectSyncView.as_view(),
        name="sync-subject-bangumi",
    ),
    path(
        "calendar/run/",
        CalendarSyncRunView.as_view(),
        name="sync-calendar-run",
    ),
    path(
        "incremental/status/",
        IncrementalSyncStatusView.as_view(),
        name="sync-incremental-status",
    ),
    path(
        "incremental/run/",
        IncrementalSyncRunView.as_view(),
        name="sync-incremental-run",
    ),
    path(
        "subjects/<uuid:subject_id>/resync/",
        SubjectResyncView.as_view(),
        name="sync-subject-resync",
    ),
]
