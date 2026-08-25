from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sync.api.serializers.import_jobs import (
    ImportJobCreateSerializer,
    ImportJobQuerySerializer,
    ImportJobSerializer,
)
from apps.sync.exceptions import SyncTaskDispatchFailed
from apps.sync.models import SyncJob
from apps.sync.services.import_providers import (
    import_provider_for,
    import_provider_for_job_type,
)
from apps.sync.services.sync_job_service import sync_job_service
from shared.api.contracts import (
    CursorPaginationQuerySerializer,
    api_responses,
    cursor_paginated_response,
)
from shared.api.pagination import TimelineCursorPagination


def import_job_data(job: SyncJob) -> dict:
    try:
        provider = import_provider_for_job_type(job.job_type).slug
    except KeyError:
        provider = "unknown"
    return {
        "id": str(job.id),
        "provider": provider,
        "external_id": job.parameters.get("external_id"),
        "status": job.status,
        "parameters": job.parameters,
        "result": job.result,
        "error": job.error or None,
        "progress": {
            "current_label": job.current_label,
            "total": job.total_count,
            "processed": job.processed_count,
            "synced": job.synced_count,
            "skipped": job.skipped_count,
            "failed": job.failed_count,
        },
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "updated_at": job.updated_at,
    }


@extend_schema_view(
    get=extend_schema(
        parameters=[ImportJobQuerySerializer, CursorPaginationQuerySerializer],
        responses=api_responses(
            {
                200: cursor_paginated_response(
                    "CursorPaginatedImportJob", ImportJobSerializer
                )
            }
        ),
    ),
    post=extend_schema(
        request=ImportJobCreateSerializer,
        responses=api_responses({202: ImportJobSerializer}),
    ),
)
class ImportJobListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        serializer = ImportJobQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        query = serializer.validated_data
        provider = query.get("provider")
        queryset = SyncJob.objects.filter(
            job_type=(
                import_provider_for(provider).job_type
                if provider is not None
                else SyncJob.JobType.VNDB_IMPORT
            )
        )
        if job_status := query.get("status"):
            queryset = queryset.filter(status=job_status)

        paginator = TimelineCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([import_job_data(job) for job in page])

    def post(self, request):
        serializer = ImportJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        provider = import_provider_for(values["provider"])
        job = sync_job_service.create_job(
            job_type=provider.job_type,
            parameters={
                "provider": provider.slug,
                "external_id": values["external_id"],
                "include_related": values["include_related"],
            },
        )
        try:
            task = provider.dispatch(
                external_id=values["external_id"],
                include_related=values["include_related"],
                job_id=str(job.id),
            )
            sync_job_service.bind_celery_task(
                job_id=job.id,
                celery_task_id=task.id,
            )
        except Exception as exc:
            sync_job_service.mark_failed(job_id=job.id, error=exc)
            raise SyncTaskDispatchFailed() from exc
        job.refresh_from_db()
        return Response(import_job_data(job), status=status.HTTP_202_ACCEPTED)


@extend_schema_view(
    get=extend_schema(responses=api_responses({200: ImportJobSerializer}))
)
class ImportJobDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, job_id):
        job = sync_job_service.get_job(job_id=job_id)
        try:
            import_provider_for_job_type(job.job_type)
        except KeyError as exc:
            raise NotFound("Import job not found.") from exc
        return Response(import_job_data(job))
