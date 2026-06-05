from django.urls import path

from apps.sync.api.views.manual_sync_view import (
    BangumiSubjectSyncView,
    CalendarSyncRunView,
    IncrementalSyncRunView,
    IncrementalSyncStatusView,
    SyncJobDetailView,
    SyncJobListView,
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
        "jobs/",
        SyncJobListView.as_view(),
        name="sync-job-list",
    ),
    path(
        "jobs/<uuid:job_id>/",
        SyncJobDetailView.as_view(),
        name="sync-job-detail",
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
