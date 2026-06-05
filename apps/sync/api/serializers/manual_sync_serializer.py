from rest_framework import serializers


class SubjectResyncRequestSerializer(serializers.Serializer):

    run_async = serializers.BooleanField(
        required=False,
        default=True,
    )


class BangumiSubjectSyncRequestSerializer(serializers.Serializer):

    bangumi_id = serializers.IntegerField(
        min_value=1,
    )
    run_async = serializers.BooleanField(
        required=False,
        default=True,
    )


class BangumiSubjectSyncQueuedResponseSerializer(serializers.Serializer):

    task_id = serializers.CharField()
    status = serializers.CharField()
    bangumi_id = serializers.IntegerField()
    job_id = serializers.UUIDField()


class SubjectResyncQueuedResponseSerializer(serializers.Serializer):

    task_id = serializers.CharField()
    status = serializers.CharField()
    subject_id = serializers.UUIDField()
    job_id = serializers.UUIDField()


class SubjectResyncResultResponseSerializer(serializers.Serializer):

    subject_id = serializers.UUIDField()
    bangumi_id = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True)
    subject_type = serializers.CharField(allow_blank=True)
    episode_synced = serializers.BooleanField()
    staff_count = serializers.IntegerField()
    character_count = serializers.IntegerField()
    related_subject_count = serializers.IntegerField()


class IncrementalSyncRunRequestSerializer(serializers.Serializer):

    run_async = serializers.BooleanField(
        required=False,
        default=True,
    )
    task_name = serializers.ChoiceField(
        required=False,
        choices=[
            "incremental_subject",
            "incremental_episode",
            "incremental_subject_subject_relation",
            "incremental_subject_staff_relation",
            "incremental_subject_character_relation",
            "incremental_character",
            "incremental_staff",
        ],
    )
    batch_size = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=100000,
    )


class IncrementalSyncQueuedResponseSerializer(serializers.Serializer):

    task_id = serializers.CharField()
    status = serializers.CharField()
    job_id = serializers.UUIDField()


class IncrementalSyncStatusResponseSerializer(serializers.Serializer):

    tasks = serializers.ListField(child=serializers.DictField())


class IncrementalSyncResultResponseSerializer(serializers.Serializer):

    results = serializers.ListField(child=serializers.DictField(), required=False)
    task_name = serializers.CharField(required=False)
    shard = serializers.CharField(required=False)
    start_id = serializers.IntegerField(required=False)
    end_id = serializers.IntegerField(required=False)
    processed_count = serializers.IntegerField(required=False)
    synced_count = serializers.IntegerField(required=False)
    skipped_count = serializers.IntegerField(required=False)
    failed_count = serializers.IntegerField(required=False)
    frontier_reached = serializers.BooleanField(required=False)


class CalendarSyncRequestSerializer(serializers.Serializer):

    run_async = serializers.BooleanField(
        required=False,
        default=True,
    )
    sync_subject_details = serializers.BooleanField(
        required=False,
        default=True,
    )


class CalendarSyncResultResponseSerializer(serializers.Serializer):

    weekday_count = serializers.IntegerField()
    item_count = serializers.IntegerField()
    synced_subject_count = serializers.IntegerField()
    failed_subject_count = serializers.IntegerField()


class SyncJobResponseSerializer(serializers.Serializer):

    id = serializers.UUIDField()
    job_type = serializers.CharField()
    status = serializers.CharField()
    celery_task_id = serializers.CharField(allow_blank=True)
    parameters = serializers.DictField()
    result = serializers.DictField(allow_null=True)
    error = serializers.CharField(allow_blank=True)
    current_label = serializers.CharField(allow_blank=True)
    total_count = serializers.IntegerField()
    processed_count = serializers.IntegerField()
    synced_count = serializers.IntegerField()
    skipped_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class SyncJobListResponseSerializer(serializers.Serializer):

    jobs = SyncJobResponseSerializer(many=True)
