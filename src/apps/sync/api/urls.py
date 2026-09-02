from django.urls import path

from apps.sync.api.views.campaigns import (
    SyncCampaignActionView,
    SyncCampaignClaimsView,
    SyncCampaignDetailView,
    SyncCampaignItemsView,
    SyncCampaignListCreateView,
    SyncCampaignSummaryView,
)
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
    path(
        "operations/sync/",
        SyncCampaignListCreateView.as_view(),
        name="sync-campaign-list",
    ),
    path(
        "operations/sync/summary/",
        SyncCampaignSummaryView.as_view(),
        name="sync-campaign-summary",
    ),
    path(
        "operations/sync/<uuid:campaign_id>/",
        SyncCampaignDetailView.as_view(),
        name="sync-campaign-detail",
    ),
    path(
        "operations/sync/<uuid:campaign_id>/items/",
        SyncCampaignItemsView.as_view(),
        name="sync-campaign-items",
    ),
    path(
        "operations/sync/<uuid:campaign_id>/claims/",
        SyncCampaignClaimsView.as_view(),
        name="sync-campaign-claims",
    ),
    path(
        "operations/sync/<uuid:campaign_id>/<str:action>/",
        SyncCampaignActionView.as_view(),
        name="sync-campaign-action",
    ),
]
