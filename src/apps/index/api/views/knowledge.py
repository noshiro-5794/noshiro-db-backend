from django.db.models import Prefetch
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.index.api.serializers.knowledge import (
    CalendarEventSerializer,
    CalendarQuerySerializer,
    EntityCharacterSerializer,
    EntityCreditSerializer,
    EntityDetailSerializer,
    EntityEpisodeSerializer,
    EntityEvidenceSerializer,
    EntityMetricSerializer,
    EntityQuerySerializer,
    EntityRelationSerializer,
    EntityReleaseSerializer,
    EntitySummarySerializer,
    IndexCollectionSerializer,
)
from apps.index.models import (
    Entity,
    IndexCollection,
    MetricSnapshot,
)
from apps.index.selectors.current import (
    current_airing_events,
    current_appearances,
    current_credits,
    current_entity_relation_evidence,
    current_entity_relations,
    current_release_work_evidence,
    current_release_work_links,
)
from apps.index.selectors.projections import (
    entity_detail,
    entity_queryset,
    entity_summary,
    field_provenance,
    preferred_name,
    request_allows_adult_content,
)
from apps.index.services import entity_resolution_service
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


class CollectionListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=api_responses({200: IndexCollectionSerializer(many=True)}, errors=()),
    )
    def get(self, request):
        return Response(
            IndexCollectionSerializer(
                [
                    {"slug": collection.slug, "name": collection.name}
                    for collection in IndexCollection.objects.filter(is_enabled=True)
                ],
                many=True,
            ).data
        )


class CollectionEntityListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[EntityQuerySerializer, PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedEntitySummary", EntitySummarySerializer
                )
            },
            errors=(400, 404),
        ),
    )
    def get(self, request, slug):
        if not IndexCollection.objects.filter(slug=slug, is_enabled=True).exists():
            raise NotFound("Index collection not found.")
        query = request.query_params.copy()
        query["collection"] = slug
        serializer = EntityQuerySerializer(data=query)
        serializer.is_valid(raise_exception=True)
        qs = entity_queryset(
            keyword=serializer.validated_data.get("query", "").strip(),
            collection=slug,
            scope="index",
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        adult_allowed = request_allows_adult_content(request)
        data = [
            entity_summary(
                item,
                language=language,
                safe=True,
                adult_allowed=adult_allowed,
            )
            for item in page
        ]
        return paginator.get_paginated_response(data)


class EntityListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[EntityQuerySerializer, PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedEntitySummary", EntitySummarySerializer
                )
            },
            errors=(400,),
        ),
    )
    def get(self, request):
        serializer = EntityQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        qs = entity_queryset(
            keyword=values.get("query", "").strip(),
            collection=values.get("collection", ""),
            scope=values.get("scope", "index"),
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        adult_allowed = request_allows_adult_content(request)
        return paginator.get_paginated_response(
            [
                entity_summary(
                    item,
                    language=language,
                    safe=True,
                    adult_allowed=adult_allowed,
                )
                for item in page
            ]
        )


class EntityDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=api_responses({200: EntityDetailSerializer}, errors=(404,)),
    )
    def get(self, request, entity_id):
        entity = ensure_public_entity(entity_id)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        data = entity_detail(
            entity,
            language=language,
            safe=True,
            adult_allowed=request_allows_adult_content(request),
        )
        return Response(EntityDetailSerializer(data).data)


class EntityRelationListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=api_responses(
            {200: EntityRelationSerializer(many=True)},
            errors=(404,),
        ),
    )
    def get(self, request, entity_id):
        entity = ensure_public_entity(entity_id)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        adult_allowed = request_allows_adult_content(request)
        cluster_ids = entity_resolution_service.cluster_ids(entity)
        relations = (
            current_entity_relations()
            .filter(
                from_entity_id__in=cluster_ids,
            )
            .select_related("to_entity")
            .prefetch_related(
                Prefetch(
                    "evidence",
                    queryset=current_entity_relation_evidence().select_related(
                        "observation__provider_record__namespace__provider",
                        "observation__mapping_run",
                    ),
                    to_attr="current_evidence",
                )
            )
        )
        data = []
        seen = set()
        for relation in relations:
            target = entity_resolution_service.resolve(relation.to_entity)
            if (
                target.lifecycle != Entity.Lifecycle.ACTIVE
                or not entity_resolution_service.is_public(target)
            ):
                continue
            key = (relation.relation_type, target.pk)
            if key in seen:
                continue
            seen.add(key)
            data.append(
                {
                    "relation_type": relation.relation_type,
                    "target": entity_summary(
                        target,
                        language=language,
                        safe=True,
                        adult_allowed=adult_allowed,
                    ),
                    "qualifiers": relation.qualifiers,
                    "evidence": [
                        {
                            **field_provenance(
                                provider_record=evidence.observation.provider_record,
                                observation=evidence.observation,
                            ),
                            "json_pointer": evidence.json_pointer,
                        }
                        for evidence in relation.current_evidence
                    ],
                }
            )
        return Response(EntityRelationSerializer(data, many=True).data)


class EntityCreditListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=api_responses(
            {200: EntityCreditSerializer(many=True)}, errors=(404,)
        ),
    )
    def get(self, request, entity_id):
        entity = ensure_public_entity(entity_id)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        adult_allowed = request_allows_adult_content(request)
        credits = (
            current_credits()
            .filter(work_id__in=entity_resolution_service.cluster_ids(entity))
            .select_related(
                "contributor__entity",
                "observation__provider_record__namespace__provider",
                "observation__mapping_run",
            )
        )
        data = []
        for credit in credits:
            contributor = entity_resolution_service.resolve(credit.contributor.entity)
            if not entity_resolution_service.is_public(contributor):
                continue
            data.append(
                {
                    "role": credit.role,
                    "credited_as": credit.credited_as,
                    "contributor": entity_summary(
                        contributor,
                        language=language,
                        safe=True,
                        adult_allowed=adult_allowed,
                    ),
                    "provenance": field_provenance(
                        provider_record=(
                            credit.observation.provider_record
                            if credit.observation_id is not None
                            else None
                        ),
                        observation=credit.observation,
                    ),
                }
            )
        return Response(EntityCreditSerializer(data, many=True).data)


class EntityEpisodeListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedEntityEpisode", EntityEpisodeSerializer
                )
            },
            errors=(404,),
        ),
    )
    def get(self, request, entity_id):
        from apps.index.models import Episode

        entity = ensure_public_entity(entity_id)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        adult_allowed = request_allows_adult_content(request)
        parent = entity_summary(entity, safe=True, adult_allowed=adult_allowed)
        parent_content_allowed = (
            adult_allowed or parent["audience"] != Entity.Audience.ADULT
        )
        episode_entity_ids = (
            current_entity_relations()
            .filter(
                from_entity_id__in=entity_resolution_service.cluster_ids(entity),
                relation_type="has-episode",
                to_entity__kind=Entity.Kind.EPISODE,
                to_entity__lifecycle=Entity.Lifecycle.ACTIVE,
            )
            .values("to_entity_id")
        )
        episodes = (
            Episode.objects.filter(
                entity_id__in=episode_entity_ids,
                entity__isnull=False,
                entity__visibility=Entity.Visibility.PUBLIC,
            )
            .distinct()
            .order_by("sort", "ep_num", "id")
        )
        paginator = DefaultPageNumberPagination()
        paginator.page_size = 64
        page = paginator.paginate_queryset(episodes, request, view=self)
        data = []
        for episode in page:
            episode_entity = entity_resolution_service.resolve(episode.entity)
            if not entity_resolution_service.is_public(episode_entity):
                continue
            detail = entity_detail(
                episode_entity,
                language=language,
                safe=True,
                adult_allowed=adult_allowed and parent_content_allowed,
            )
            descriptions = detail["descriptions"] if parent_content_allowed else []
            representation = (
                episode_entity.provider_representations.filter(is_active=True)
                .select_related(
                    "provider_record__namespace__provider",
                    "provider_record__latest_revision",
                )
                .order_by(
                    "provider_record__namespace__provider__slug",
                    "provider_record__external_id",
                )
                .first()
            )
            observation = None
            if representation is not None:
                observation = (
                    representation.provider_record.current_observations.filter(
                        schema_name="index.episode"
                    )
                    .select_related("observation__mapping_run")
                    .first()
                )
                observation = (
                    observation.observation if observation is not None else None
                )
            data.append(
                {
                    "id": str(episode_entity.id),
                    "title": preferred_name(episode_entity, language=language),
                    "title_cn": preferred_name(episode_entity, language="zh-Hans"),
                    "type": episode.type,
                    "number": episode.ep_num,
                    "sort": episode.sort,
                    "disc": episode.disc,
                    "duration": episode.duration,
                    "raw_duration": episode.raw_duration,
                    "air_date": episode.date,
                    "comment_count": episode.comment_count,
                    "description": descriptions[0]["text"] if descriptions else "",
                    "provenance": field_provenance(
                        provider_record=(
                            representation.provider_record
                            if representation is not None
                            else None
                        ),
                        observation=observation,
                    ),
                }
            )
        return paginator.get_paginated_response(data)


class EntityCharacterListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {
                200: paginated_response(
                    "PaginatedEntityCharacter", EntityCharacterSerializer
                )
            },
            errors=(404,),
        ),
    )
    def get(self, request, entity_id):
        entity = ensure_public_entity(entity_id)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        adult_allowed = request_allows_adult_content(request)
        appearances = (
            current_appearances()
            .filter(
                work_id__in=entity_resolution_service.cluster_ids(entity),
                spoiler_level=0,
                character_entity__visibility=Entity.Visibility.PUBLIC,
            )
            .select_related(
                "character_entity",
                "observation__provider_record__namespace__provider",
                "observation__mapping_run",
            )
            .order_by("role", "character_entity_id", "id")
        )
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(appearances, request, view=self)
        data = []
        for appearance in page:
            character = entity_resolution_service.resolve(appearance.character_entity)
            if not entity_resolution_service.is_public(character):
                continue
            data.append(
                {
                    "role": appearance.role,
                    "spoiler_level": appearance.spoiler_level,
                    "character": entity_summary(
                        character,
                        language=language,
                        safe=True,
                        adult_allowed=adult_allowed,
                    ),
                    "provenance": field_provenance(
                        provider_record=(
                            appearance.observation.provider_record
                            if appearance.observation_id is not None
                            else None
                        ),
                        observation=appearance.observation,
                    ),
                }
            )
        return paginator.get_paginated_response(data)


class EntityReleaseListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=api_responses(
            {200: EntityReleaseSerializer(many=True)}, errors=(404,)
        ),
    )
    def get(self, request, entity_id):
        entity = ensure_public_entity(entity_id)
        language = request.headers.get("Accept-Language", "").split(",", 1)[0]
        adult_allowed = request_allows_adult_content(request)
        links = (
            current_release_work_links()
            .filter(work_id__in=entity_resolution_service.cluster_ids(entity))
            .select_related("release__entity")
            .prefetch_related(
                Prefetch(
                    "evidence",
                    queryset=current_release_work_evidence().select_related(
                        "observation__provider_record__namespace__provider",
                        "observation__mapping_run",
                    ),
                    to_attr="current_evidence",
                )
            )
        )
        data = []
        for link in links:
            release_entity = entity_resolution_service.resolve(link.release.entity)
            if not entity_resolution_service.is_public(release_entity):
                continue
            data.append(
                {
                    "role": link.role,
                    "release": entity_summary(
                        release_entity,
                        language=language,
                        safe=True,
                        adult_allowed=adult_allowed,
                    ),
                    "date_start": link.release.date_start,
                    "date_end": link.release.date_end,
                    "date_precision": link.release.date_precision,
                    "date_raw": link.release.date_raw,
                    "platform": link.release.platform,
                    "region": link.release.region,
                    "evidence": [
                        {
                            **field_provenance(
                                provider_record=evidence.observation.provider_record,
                                observation=evidence.observation,
                            ),
                            "json_pointer": evidence.json_pointer,
                        }
                        for evidence in link.current_evidence
                    ],
                }
            )
        return Response(data)


class EntityMetricListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=api_responses(
            {200: EntityMetricSerializer(many=True)}, errors=(404,)
        ),
    )
    def get(self, request, entity_id):
        entity = ensure_public_entity(entity_id)
        snapshots = (
            MetricSnapshot.objects.filter(
                entity_id__in=entity_resolution_service.cluster_ids(entity)
            )
            .exclude(
                provider_record__namespace__provider__redistribution_policy="forbidden"
            )
            .select_related("provider_record__namespace__provider")
            .order_by("metric", "-observed_at")
        )
        return Response(
            [
                {
                    "metric": snapshot.metric,
                    "value": snapshot.value,
                    "sample_size": snapshot.sample_size,
                    "observed_at": snapshot.observed_at,
                    "provider": snapshot.provider_record.namespace.provider.slug,
                }
                for snapshot in snapshots
            ]
        )


class EntityEvidenceListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=api_responses(
            {200: EntityEvidenceSerializer(many=True)},
            errors=(404,),
        ),
    )
    def get(self, request, entity_id):
        entity = entity_resolution_service.resolve(ensure_public_entity(entity_id))
        return Response(
            [
                {
                    "provider": item.provider_record.namespace.provider.slug,
                    "namespace": item.provider_record.namespace.slug,
                    "external_id": item.provider_record.external_id,
                    "revision_id": (
                        str(item.provider_record.latest_revision_id)
                        if item.provider_record.latest_revision_id
                        else None
                    ),
                    "observed_at": item.created_at,
                }
                for item in entity.provider_representations.model.objects.filter(
                    entity_id__in=entity_resolution_service.cluster_ids(entity),
                    is_active=True,
                )
                .exclude(
                    provider_record__namespace__provider__redistribution_policy=(
                        "forbidden"
                    )
                )
                .select_related("provider_record__namespace__provider")
            ]
        )


class CalendarEventListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATETIME),
            OpenApiParameter("to", OpenApiTypes.DATETIME),
            OpenApiParameter("timezone", OpenApiTypes.STR),
        ],
        responses=api_responses(
            {200: CalendarEventSerializer(many=True)}, errors=(400,)
        ),
    )
    def get(self, request):
        query = {
            "from_": request.query_params.get("from"),
            "to": request.query_params.get("to"),
            "timezone": request.query_params.get("timezone"),
        }
        query = {key: value for key, value in query.items() if value not in (None, "")}
        serializer = CalendarQuerySerializer(data=query)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        qs = (
            current_airing_events()
            .filter(
                work__entity__lifecycle=Entity.Lifecycle.ACTIVE,
                work__entity__visibility=Entity.Visibility.PUBLIC,
            )
            .select_related(
                "work__entity",
                "episode_entity",
                "observation__provider_record__namespace__provider",
                "observation__mapping_run",
            )
        )
        if from_value := values.get("from"):
            qs = qs.filter(starts_at__gte=from_value)
        if to_value := values.get("to"):
            qs = qs.filter(starts_at__lte=to_value)
        if timezone := values.get("timezone"):
            qs = qs.filter(timezone=timezone)
        adult_allowed = request_allows_adult_content(request)
        data = []
        seen = set()
        for event in qs.order_by("starts_at", "id"):
            work_entity = entity_resolution_service.resolve(event.work.entity)
            if not entity_resolution_service.is_public(work_entity):
                continue
            summary = entity_summary(
                work_entity,
                safe=True,
                adult_allowed=adult_allowed,
            )
            if summary["audience"] == Entity.Audience.ADULT and not adult_allowed:
                continue
            episode_id = None
            if event.episode_entity_id is not None:
                episode = entity_resolution_service.resolve(event.episode_entity)
                if not entity_resolution_service.is_public(episode):
                    continue
                episode_id = episode.id
            key = (
                work_entity.id,
                episode_id,
                event.starts_at,
                event.weekday,
                event.region,
            )
            if key in seen:
                continue
            seen.add(key)
            data.append(
                {
                    "id": event.id,
                    "work_id": work_entity.id,
                    "episode_id": episode_id,
                    "starts_at": event.starts_at,
                    "timezone": event.timezone,
                    "region": event.region,
                    "weekday": event.weekday,
                    "precision": event.precision,
                    "raw_value": event.raw_value,
                    "provenance": field_provenance(
                        provider_record=(
                            event.observation.provider_record
                            if event.observation_id is not None
                            else None
                        ),
                        observation=event.observation,
                    ),
                }
            )
        return Response(CalendarEventSerializer(data, many=True).data)


def ensure_public_entity(entity_id) -> Entity:
    try:
        entity = Entity.objects.get(pk=entity_id)
    except Entity.DoesNotExist as exc:
        raise NotFound("Entity not found.") from exc
    entity = entity_resolution_service.resolve(entity)
    if (
        entity.lifecycle != Entity.Lifecycle.ACTIVE
        or not entity_resolution_service.is_public(entity)
    ):
        raise NotFound("Entity not found.")
    return entity
