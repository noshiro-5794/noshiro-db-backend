from django.urls import path

from apps.sync.api.views.import_jobs import ImportJobDetailView, ImportJobListCreateView

urlpatterns = [
    path(
        "operations/import-jobs/",
        ImportJobListCreateView.as_view(),
        name="import-job-list",
    ),
    path(
        "operations/import-jobs/<uuid:job_id>/",
        ImportJobDetailView.as_view(),
        name="import-job-detail",
    ),
]
