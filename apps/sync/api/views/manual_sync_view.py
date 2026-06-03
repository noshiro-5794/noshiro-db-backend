from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from apps.core.response import success_response
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
)
from apps.sync.exceptions import SyncTaskDispatchFailed
from apps.sync.services.calendar_service import calendar_sync_service
from apps.sync.services.incremental_sync_service import incremental_sync_service
from apps.sync.services.manual_sync_service import manual_subject_sync_service
from apps.sync.tasks.calendar import sync_calendar_task
from apps.sync.tasks.incremental import run_incremental_sync_task
from apps.sync.tasks.manual import sync_subject_by_bangumi_id_task, sync_subject_by_uuid_task


class BangumiSubjectSyncView(APIView):

    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = BangumiSubjectSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bangumi_id = serializer.validated_data["bangumi_id"]
        run_async = serializer.validated_data["run_async"]

        if run_async:
            try:
                task = sync_subject_by_bangumi_id_task.delay(bangumi_id)
            except Exception as exc:
                raise SyncTaskDispatchFailed() from exc

            output_serializer = BangumiSubjectSyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "bangumi_id": bangumi_id,
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        result = manual_subject_sync_service.sync_by_bangumi_id(
            bangumi_id=bangumi_id,
        )
        output_serializer = SubjectResyncResultResponseSerializer(result)
        return success_response(data=output_serializer.data)


class SubjectResyncView(APIView):

    permission_classes = [IsAdminUser]

    def post(self, request, subject_id):
        serializer = SubjectResyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run_async = serializer.validated_data["run_async"]
        if run_async:
            try:
                task = sync_subject_by_uuid_task.delay(str(subject_id))
            except Exception as exc:
                raise SyncTaskDispatchFailed() from exc

            output_serializer = SubjectResyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                    "subject_id": subject_id,
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        result = manual_subject_sync_service.sync_by_uuid(
            subject_id=subject_id,
        )
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

        if run_async:
            try:
                task = run_incremental_sync_task.delay(
                    task_name=task_name,
                    batch_size=batch_size,
                )
            except Exception as exc:
                raise SyncTaskDispatchFailed() from exc

            output_serializer = IncrementalSyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        if task_name:
            result = incremental_sync_service.sync_task(
                task_name=task_name,
                batch_size=batch_size,
            )
        else:
            result = incremental_sync_service.sync_all(batch_size=batch_size)
        output_serializer = IncrementalSyncResultResponseSerializer(result)
        return success_response(data=output_serializer.data)


class CalendarSyncRunView(APIView):

    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = CalendarSyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        run_async = serializer.validated_data["run_async"]
        sync_subject_details = serializer.validated_data["sync_subject_details"]

        if run_async:
            try:
                task = sync_calendar_task.delay(
                    sync_subject_details=sync_subject_details,
                )
            except Exception as exc:
                raise SyncTaskDispatchFailed() from exc

            output_serializer = IncrementalSyncQueuedResponseSerializer(
                {
                    "task_id": task.id,
                    "status": "queued",
                }
            )
            return success_response(
                data=output_serializer.data,
                status_code=status.HTTP_202_ACCEPTED,
            )

        result = calendar_sync_service.sync_calendar(
            sync_subject_details=sync_subject_details,
        )
        output_serializer = CalendarSyncResultResponseSerializer(result)
        return success_response(data=output_serializer.data)
