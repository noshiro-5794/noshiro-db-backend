from django.urls import path

from apps.index.api.views.knowledge import (
    CalendarEventListView,
    CollectionEntityListView,
    CollectionListView,
    EntityCharacterListView,
    EntityCreditListView,
    EntityDetailView,
    EntityEpisodeListView,
    EntityEvidenceListView,
    EntityListView,
    EntityMetricListView,
    EntityRelationListView,
    EntityReleaseListView,
)

urlpatterns = [
    path("index/collections/", CollectionListView.as_view(), name="index-collections"),
    path(
        "index/collections/<slug:slug>/entities/",
        CollectionEntityListView.as_view(),
        name="index-collection-entities",
    ),
    path("index/entities/", EntityListView.as_view(), name="index-entities"),
    path(
        "index/entities/<uuid:entity_id>/",
        EntityDetailView.as_view(),
        name="index-entity",
    ),
    path(
        "index/entities/<uuid:entity_id>/episodes/",
        EntityEpisodeListView.as_view(),
        name="index-entity-episodes",
    ),
    path(
        "index/entities/<uuid:entity_id>/relations/",
        EntityRelationListView.as_view(),
        name="index-entity-relations",
    ),
    path(
        "index/entities/<uuid:entity_id>/characters/",
        EntityCharacterListView.as_view(),
        name="index-entity-characters",
    ),
    path(
        "index/entities/<uuid:entity_id>/credits/",
        EntityCreditListView.as_view(),
        name="index-entity-credits",
    ),
    path(
        "index/entities/<uuid:entity_id>/releases/",
        EntityReleaseListView.as_view(),
        name="index-entity-releases",
    ),
    path(
        "index/entities/<uuid:entity_id>/metrics/",
        EntityMetricListView.as_view(),
        name="index-entity-metrics",
    ),
    path(
        "index/entities/<uuid:entity_id>/evidence/",
        EntityEvidenceListView.as_view(),
        name="index-entity-evidence",
    ),
    path(
        "index/calendar/events/",
        CalendarEventListView.as_view(),
        name="index-calendar-events",
    ),
]
