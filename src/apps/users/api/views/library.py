from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.index.models import Entity, Release
from apps.index.selectors.projections import (
    entity_detail,
    entity_summary,
    preferred_name,
)
from apps.index.services import entity_resolution_service
from apps.users.api.serializers.contracts import (
    EpisodeProgressReplaceSerializer,
    EpisodeProgressSerializer,
    LibraryEntryQuerySerializer,
    LibraryEntrySerializer,
    LibraryEntryWriteSerializer,
    RatingDetailSerializer,
    ReleaseStateSerializer,
    ReleaseStateWriteSerializer,
)
from apps.users.api.serializers.rating_details import (
    UserSubjectRatingDetailReplaceRequestSerializer,
    UserSubjectRatingDetailResponseSerializer,
)
from apps.users.api.serializers.tags import (
    UserSubjectTagReplaceRequestSerializer,
    UserTagCreateRequestSerializer,
    UserTagResponseSerializer,
    UserTagUpdateRequestSerializer,
)
from apps.users.models import (
    UserEpisodeProgress,
    UserRelease,
    UserSubject,
    UserSubjectRatingDetail,
    UserSubjectTag,
    UserTag,
)
from shared.api.contracts import (
    PaginationQuerySerializer,
    api_responses,
    paginated_response,
)
from shared.api.pagination import DefaultPageNumberPagination


def library_entry_queryset(*, user):
    return (
        UserSubject.objects.filter(user=user, entity__isnull=False)
        .select_related("entity", "entity__work")
        .prefetch_related(
            "entity__names",
            "entity__media__asset",
            "entity__index_memberships__collection",
            "release_states",
        )
    )


def library_entry_entity_ids(entry: UserSubject) -> set:
    return entity_resolution_service.cluster_ids(entry.entity)


def get_library_entry(*, user, entry_id: int, for_update: bool = False) -> UserSubject:
    queryset = library_entry_queryset(user=user)
    if for_update:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=entry_id)
    except UserSubject.DoesNotExist as exc:
        raise NotFound("Library entry not found.") from exc


def release_state_data(state: UserRelease) -> dict:
    return {
        "release_id": str(state.release_id),
        "status": state.status,
        "language": state.language,
        "platform": state.platform,
        "note": state.note,
        "started_at": state.started_at,
        "completed_at": state.completed_at,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
    }


def library_entry_data(entry: UserSubject) -> dict:
    return {
        "id": entry.id,
        "entity": entity_summary(entry.entity, safe=True),
        "status": entry.status,
        "simple_rating": entry.simple_rating,
        "rating": entry.rating,
        "comment": entry.comment,
        "watch_start_date": entry.watch_start_date,
        "watch_end_date": entry.watch_end_date,
        "is_public": entry.is_public,
        "releases": [release_state_data(state) for state in entry.release_states.all()],
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def validate_watch_dates(*, entry: UserSubject | None, values: dict) -> None:
    start = values.get(
        "watch_start_date", entry.watch_start_date if entry is not None else None
    )
    end = values.get(
        "watch_end_date", entry.watch_end_date if entry is not None else None
    )
    if start and end and start > end:
        raise ValidationError(
            {"watch_end_date": "Must not be earlier than watch_start_date."}
        )


@extend_schema_view(
    get=extend_schema(
        parameters=[LibraryEntryQuerySerializer, PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedLibraryEntry", LibraryEntrySerializer)}
        ),
    ),
    post=extend_schema(
        request=LibraryEntryWriteSerializer,
        responses=api_responses(
            {200: LibraryEntrySerializer, 201: LibraryEntrySerializer}
        ),
    ),
)
class LibraryEntryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = LibraryEntryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        queryset = library_entry_queryset(user=request.user)
        if entry_status := serializer.validated_data.get("status"):
            queryset = queryset.filter(status=entry_status)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(
            queryset.order_by("-updated_at", "-id"), request, view=self
        )
        return paginator.get_paginated_response(
            [library_entry_data(entry) for entry in page]
        )

    @transaction.atomic
    def post(self, request):
        serializer = LibraryEntryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        entity_id = values.pop("entity_id", None)
        if entity_id is None or "status" not in values:
            raise ValidationError({"entity_id": "entity_id and status are required."})
        validate_watch_dates(entry=None, values=values)
        try:
            entity = Entity.objects.select_related("work").get(pk=entity_id)
        except Entity.DoesNotExist as exc:
            raise ValidationError(
                {"entity_id": "A current Work entity is required."}
            ) from exc
        entity = entity_resolution_service.resolve(entity)
        if (
            entity.kind != Entity.Kind.WORK
            or entity.lifecycle != Entity.Lifecycle.ACTIVE
        ):
            raise ValidationError({"entity_id": "A current Work entity is required."})

        cluster_ids = entity_resolution_service.cluster_ids(entity)
        entry = (
            UserSubject.objects.select_for_update()
            .filter(user=request.user, entity_id__in=cluster_ids)
            .first()
        )
        created = entry is None
        if entry is None:
            entry = UserSubject.objects.create(
                user=request.user,
                entity=entity,
                **values,
            )
        else:
            for field, value in values.items():
                setattr(entry, field, value)
            entry.save(update_fields=[*values, "updated_at"])
        entry = get_library_entry(user=request.user, entry_id=entry.id)
        return Response(
            library_entry_data(entry),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@extend_schema_view(
    get=extend_schema(responses=api_responses({200: LibraryEntrySerializer})),
    patch=extend_schema(
        request=LibraryEntryWriteSerializer,
        responses=api_responses({200: LibraryEntrySerializer}),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class LibraryEntryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entry_id: int):
        return Response(
            library_entry_data(get_library_entry(user=request.user, entry_id=entry_id))
        )

    @transaction.atomic
    def patch(self, request, entry_id: int):
        serializer = LibraryEntryWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        entry = get_library_entry(user=request.user, entry_id=entry_id, for_update=True)
        values = dict(serializer.validated_data)
        values.pop("entity_id", None)
        validate_watch_dates(entry=entry, values=values)
        for field, value in values.items():
            setattr(entry, field, value)
        if values:
            entry.save(update_fields=[*values, "updated_at"])
        return Response(
            library_entry_data(get_library_entry(user=request.user, entry_id=entry_id))
        )

    def delete(self, request, entry_id: int):
        get_library_entry(user=request.user, entry_id=entry_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    put=extend_schema(
        request=ReleaseStateWriteSerializer,
        responses=api_responses(
            {200: ReleaseStateSerializer, 201: ReleaseStateSerializer}
        ),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class LibraryEntryReleaseView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def put(self, request, entry_id: int, release_id):
        serializer = ReleaseStateWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = get_library_entry(user=request.user, entry_id=entry_id, for_update=True)
        try:
            release = Release.objects.get(
                pk=release_id,
                work_links__work_id__in=library_entry_entity_ids(entry),
            )
        except Release.DoesNotExist as exc:
            raise NotFound("Release not found for this Work.") from exc
        state, created = UserRelease.objects.update_or_create(
            library_entry=entry,
            release=release,
            defaults=serializer.validated_data,
        )
        return Response(
            release_state_data(state),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, entry_id: int, release_id):
        entry = get_library_entry(user=request.user, entry_id=entry_id)
        deleted, _ = UserRelease.objects.filter(
            library_entry=entry, release_id=release_id
        ).delete()
        if not deleted:
            raise NotFound("Release state not found.")
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        parameters=[PaginationQuerySerializer],
        responses=api_responses(
            {200: paginated_response("PaginatedUserTag", UserTagResponseSerializer)}
        ),
    ),
    post=extend_schema(
        request=UserTagCreateRequestSerializer,
        responses=api_responses(
            {200: UserTagResponseSerializer, 201: UserTagResponseSerializer}
        ),
    ),
)
class UserTagListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = UserTag.objects.filter(user=request.user).order_by("name", "id")
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            UserTagResponseSerializer(page, many=True).data
        )

    def post(self, request):
        serializer = UserTagCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tag, created = UserTag.objects.get_or_create(
            user=request.user, name=serializer.validated_data["name"]
        )
        return Response(
            UserTagResponseSerializer(tag).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


@extend_schema_view(
    patch=extend_schema(
        request=UserTagUpdateRequestSerializer,
        responses=api_responses({200: UserTagResponseSerializer}),
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class UserTagDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, tag_id: int):
        serializer = UserTagUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tag = UserTag.objects.get(user=request.user, pk=tag_id)
        except UserTag.DoesNotExist as exc:
            raise NotFound("Tag not found.") from exc
        tag.name = serializer.validated_data["name"]
        tag.save(update_fields=["name"])
        return Response(UserTagResponseSerializer(tag).data)

    def delete(self, request, tag_id: int):
        deleted, _ = UserTag.objects.filter(user=request.user, pk=tag_id).delete()
        if not deleted:
            raise NotFound("Tag not found.")
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        responses=api_responses({200: UserTagResponseSerializer(many=True)})
    ),
    put=extend_schema(
        request=UserSubjectTagReplaceRequestSerializer,
        responses=api_responses({200: UserTagResponseSerializer(many=True)}),
    ),
)
class LibraryEntryTagView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entry_id: int):
        entry = get_library_entry(user=request.user, entry_id=entry_id)
        tags = UserTag.objects.filter(subject_relations__user_subject=entry).order_by(
            "name", "id"
        )
        return Response(UserTagResponseSerializer(tags, many=True).data)

    @transaction.atomic
    def put(self, request, entry_id: int):
        serializer = UserSubjectTagReplaceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = get_library_entry(user=request.user, entry_id=entry_id, for_update=True)
        tag_ids = list(dict.fromkeys(serializer.validated_data.get("tag_ids", [])))
        tags = list(UserTag.objects.filter(user=request.user, id__in=tag_ids))
        if {tag.id for tag in tags} != set(tag_ids):
            raise ValidationError({"tag_ids": "Contains an unknown tag."})
        for name in serializer.validated_data.get("tag_names", []):
            tag, _ = UserTag.objects.get_or_create(user=request.user, name=name)
            if tag.id not in {item.id for item in tags}:
                tags.append(tag)
        UserSubjectTag.objects.filter(user_subject=entry).delete()
        UserSubjectTag.objects.bulk_create(
            [UserSubjectTag(user_subject=entry, tag=tag) for tag in tags]
        )
        return Response(UserTagResponseSerializer(tags, many=True).data)


@extend_schema_view(
    get=extend_schema(
        responses=api_responses({200: RatingDetailSerializer(many=True)})
    ),
    put=extend_schema(
        request=UserSubjectRatingDetailReplaceRequestSerializer,
        responses=api_responses({200: RatingDetailSerializer(many=True)}),
    ),
)
class LibraryEntryRatingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entry_id: int):
        entry = get_library_entry(user=request.user, entry_id=entry_id)
        details = entry.rating_details.order_by("id")
        return Response(
            UserSubjectRatingDetailResponseSerializer(details, many=True).data
        )

    @transaction.atomic
    def put(self, request, entry_id: int):
        serializer = UserSubjectRatingDetailReplaceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = get_library_entry(user=request.user, entry_id=entry_id, for_update=True)
        UserSubjectRatingDetail.objects.filter(user_subject=entry).delete()
        details = UserSubjectRatingDetail.objects.bulk_create(
            [
                UserSubjectRatingDetail(user_subject=entry, **item)
                for item in serializer.validated_data["details"]
            ]
        )
        return Response(
            UserSubjectRatingDetailResponseSerializer(details, many=True).data
        )


def entry_episodes(entry: UserSubject):
    from apps.index.selectors.current import current_entity_relations

    episode_entity_ids = (
        current_entity_relations()
        .filter(
            from_entity_id__in=library_entry_entity_ids(entry),
            relation_type="has-episode",
            to_entity__kind=Entity.Kind.EPISODE,
            to_entity__lifecycle=Entity.Lifecycle.ACTIVE,
        )
        .values("to_entity_id")
    )
    return (
        Entity.objects.filter(
            id__in=episode_entity_ids,
            kind=Entity.Kind.EPISODE,
            lifecycle=Entity.Lifecycle.ACTIVE,
        )
        .distinct()
        .order_by("id")
    )


def episode_progress_data(*, entry: UserSubject) -> dict:
    episodes = list(entry_episodes(entry))
    finished_ids = set(
        UserEpisodeProgress.objects.filter(
            user_subject=entry, is_finished=True
        ).values_list("episode_entity_id", flat=True)
    )
    items = [
        {
            "id": str(episode.id),
            "title": preferred_name(episode),
            "title_cn": preferred_name(episode, language="zh-Hans"),
            "type": next(
                (
                    fact["value"]
                    for fact in entity_detail(episode, safe=True)["facts"]
                    if fact["predicate"] == "episode-type"
                ),
                "",
            ),
            "number": next(
                (
                    fact["value"]
                    for fact in entity_detail(episode, safe=True)["facts"]
                    if fact["predicate"] == "episode-number"
                ),
                None,
            ),
            "sort": next(
                (
                    fact["value"]
                    for fact in entity_detail(episode, safe=True)["facts"]
                    if fact["predicate"] == "sort"
                ),
                None,
            ),
            "air_date": next(
                (
                    fact["value"]
                    for fact in entity_detail(episode, safe=True)["facts"]
                    if fact["predicate"] == "air-date"
                ),
                None,
            ),
            "is_finished": episode.id in finished_ids,
        }
        for episode in episodes
    ]
    return {
        "library_entry_id": entry.id,
        "entity_id": str(entity_resolution_service.resolve(entry.entity).id),
        "total_episodes": len(items),
        "finished_count": len(finished_ids),
        "finished_episode_ids": [item["id"] for item in items if item["is_finished"]],
        "episodes": items,
    }


@extend_schema_view(
    get=extend_schema(responses=api_responses({200: EpisodeProgressSerializer})),
    put=extend_schema(
        request=EpisodeProgressReplaceSerializer,
        responses=api_responses({200: EpisodeProgressSerializer}),
    ),
)
class LibraryEntryEpisodeProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, entry_id: int):
        return Response(
            episode_progress_data(
                entry=get_library_entry(user=request.user, entry_id=entry_id)
            )
        )

    @transaction.atomic
    def put(self, request, entry_id: int):
        serializer = EpisodeProgressReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = get_library_entry(user=request.user, entry_id=entry_id, for_update=True)
        requested_ids = serializer.validated_data["finished_episode_ids"]
        episodes = list(entry_episodes(entry).filter(id__in=requested_ids))
        if {episode.id for episode in episodes} != set(requested_ids):
            raise ValidationError(
                {"finished_episode_ids": "Contains an episode outside this Work."}
            )
        UserEpisodeProgress.objects.filter(user_subject=entry).delete()
        UserEpisodeProgress.objects.bulk_create(
            [
                UserEpisodeProgress(
                    user_subject=entry,
                    episode_entity=episode,
                    is_finished=True,
                )
                for episode in episodes
            ]
        )
        return Response(episode_progress_data(entry=entry))


@extend_schema_view(
    put=extend_schema(
        request=None, responses=api_responses({200: EpisodeProgressSerializer})
    ),
    delete=extend_schema(responses=api_responses({204: None})),
)
class LibraryEntryEpisodeProgressItemView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def put(self, request, entry_id: int, episode_id):
        entry = get_library_entry(user=request.user, entry_id=entry_id, for_update=True)
        try:
            episode = entry_episodes(entry).get(pk=episode_id)
        except Entity.DoesNotExist as exc:
            raise NotFound("Episode not found for this Work.") from exc
        UserEpisodeProgress.objects.update_or_create(
            user_subject=entry,
            episode_entity=episode,
            defaults={"is_finished": True},
        )
        return Response(episode_progress_data(entry=entry))

    def delete(self, request, entry_id: int, episode_id):
        entry = get_library_entry(user=request.user, entry_id=entry_id)
        UserEpisodeProgress.objects.filter(
            user_subject=entry, episode_entity_id=episode_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
