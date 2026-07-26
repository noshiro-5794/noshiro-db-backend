from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from apps.sync.api.serializers.manual_sync_serializer import (
    BangumiSubjectSyncQueuedResponseSerializer,
    BangumiSubjectSyncRequestSerializer,
    CalendarSyncRequestSerializer,
    CalendarSyncResultResponseSerializer,
    IncrementalSyncQueuedResponseSerializer,
    IncrementalSyncResultResponseSerializer,
    IncrementalSyncRunRequestSerializer,
    IncrementalSyncStatusResponseSerializer,
    SubjectResyncQueuedResponseSerializer,
    SubjectResyncRequestSerializer,
    SubjectResyncResultResponseSerializer,
    SyncJobListRequestSerializer,
    SyncJobResponseSerializer,
)
from apps.sync.exceptions import SyncTaskDispatchFailed
from apps.sync.models import SyncJob
from apps.sync.services.calendar_service import calendar_sync_service
from apps.sync.services.incremental_sync_service import incremental_sync_service
from apps.sync.services.manual_sync_service import manual_subject_sync_service
from apps.sync.services.sync_job_service import sync_job_service
from apps.sync.tasks.calendar import sync_calendar_task
from apps.sync.tasks.incremental import run_incremental_sync_task
from apps.sync.tasks.manual import (
    sync_subject_by_bangumi_id_task,
    sync_subject_by_uuid_task,
)
from shared.api.pagination import DefaultPageNumberPagination
from shared.api.responses import success_response


class BangumiSubjectSyncView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = BangumiSubjectSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bangumi_id = serializer.validated_data["bangumi_id"]
        run_async = serializer.validated_data["run_async"]
        job = sync_job_service.create_job(
            job_type=SyncJob.JobType.SUBJECT_BANGUMI,
            parameters={"bangumi_id": bangumi_id, "run_async": run_async},
        )

        if run_async:
            try:
                task = sync_subject_by_bangumi_id_task.delay(
                    bangumi_id,
                    job_id=str(job.id),
                )
                sync_job_service.bind_celery_task(
                    job_id=job.id,
                    celery_task_id=task.id,
                )
            except Exception as exc:
                sync_job_service.mark_failed(job_id=job.id, error=exc)
                raise SyncTaskDispatchFailed() from exc

            output_serializer = BangumiSubjectSyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "bangumi_id": bangumi_id,
                    "job_id": job.id,
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        try:
            result = manual_subject_sync_service.sync_by_bangumi_id(
                bangumi_id=bangumi_id,
                job_id=job.id,
            )
        except Exception as exc:
            sync_job_service.mark_failed(job_id=job.id, error=exc)
            raise
        output_serializer = SubjectResyncResultResponseSerializer(result)
        return success_response(data=output_serializer.data)


class SubjectResyncView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, subject_id):
        serializer = SubjectResyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run_async = serializer.validated_data["run_async"]
        job = sync_job_service.create_job(
            job_type=SyncJob.JobType.SUBJECT_RESYNC,
            parameters={"subject_id": str(subject_id), "run_async": run_async},
        )
        if run_async:
            try:
                task = sync_subject_by_uuid_task.delay(
                    str(subject_id),
                    job_id=str(job.id),
                )
                sync_job_service.bind_celery_task(
                    job_id=job.id,
                    celery_task_id=task.id,
                )
            except Exception as exc:
                sync_job_service.mark_failed(job_id=job.id, error=exc)
                raise SyncTaskDispatchFailed() from exc

            output_serializer = SubjectResyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "subject_id": subject_id,
                    "job_id": job.id,
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        try:
            result = manual_subject_sync_service.sync_by_uuid(
                subject_id=subject_id,
                job_id=job.id,
            )
        except Exception as exc:
            sync_job_service.mark_failed(job_id=job.id, error=exc)
            raise
        output_serializer = SubjectResyncResultResponseSerializer(result)
        return success_response(data=output_serializer.data)


class IncrementalSyncStatusView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_data = incremental_sync_service.get_status()
        serializer = IncrementalSyncStatusResponseSerializer(status_data)
        return success_response(data=serializer.data)


class IncrementalSyncRunView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = IncrementalSyncRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run_async = serializer.validated_data["run_async"]
        batch_size = serializer.validated_data.get("batch_size")
        task_name = serializer.validated_data.get("task_name")
        job = sync_job_service.create_job(
            job_type=SyncJob.JobType.INCREMENTAL,
            parameters={
                "run_async": run_async,
                "batch_size": batch_size,
                "task_name": task_name,
            },
        )

        if run_async:
            try:
                task = run_incremental_sync_task.delay(
                    task_name=task_name,
                    batch_size=batch_size,
                    job_id=str(job.id),
                )
                sync_job_service.bind_celery_task(
                    job_id=job.id,
                    celery_task_id=task.id,
                )
            except Exception as exc:
                sync_job_service.mark_failed(job_id=job.id, error=exc)
                raise SyncTaskDispatchFailed() from exc

            output_serializer = IncrementalSyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "job_id": job.id,
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        try:
            if task_name:
                result = incremental_sync_service.sync_task(
                    task_name=task_name,
                    batch_size=batch_size,
                    job_id=job.id,
                )
            else:
                result = incremental_sync_service.sync_all(
                    batch_size=batch_size,
                    job_id=job.id,
                )
            sync_job_service.mark_succeeded(
                job_id=job.id,
                result=result,
                current_label="Incremental sync completed",
            )
        except Exception as exc:
            sync_job_service.mark_failed(job_id=job.id, error=exc)
            raise
        output_serializer = IncrementalSyncResultResponseSerializer(result)
        return success_response(data=output_serializer.data)


class CalendarSyncRunView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = CalendarSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run_async = serializer.validated_data["run_async"]
        sync_subject_details = serializer.validated_data["sync_subject_details"]
        job = sync_job_service.create_job(
            job_type=SyncJob.JobType.CALENDAR,
            parameters={
                "run_async": run_async,
                "sync_subject_details": sync_subject_details,
            },
        )

        if run_async:
            try:
                task = sync_calendar_task.delay(
                    sync_subject_details=sync_subject_details,
                    job_id=str(job.id),
                )
                sync_job_service.bind_celery_task(
                    job_id=job.id,
                    celery_task_id=task.id,
                )
            except Exception as exc:
                sync_job_service.mark_failed(job_id=job.id, error=exc)
                raise SyncTaskDispatchFailed() from exc

            output_serializer = IncrementalSyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "job_id": job.id,
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        try:
            result = calendar_sync_service.sync_calendar(
                sync_subject_details=sync_subject_details,
                job_id=job.id,
            )
        except Exception as exc:
            sync_job_service.mark_failed(job_id=job.id, error=exc)
            raise
        output_serializer = CalendarSyncResultResponseSerializer(result)
        return success_response(data=output_serializer.data)


class SyncJobListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        query_serializer = SyncJobListRequestSerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = sync_job_service.list_queryset(
            **query_serializer.validated_data,
        )

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = SyncJobResponseSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class SyncJobDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, job_id):
        job = sync_job_service.get_job(job_id=job_id)
        serializer = SyncJobResponseSerializer(job)
        return success_response(data=serializer.data)
