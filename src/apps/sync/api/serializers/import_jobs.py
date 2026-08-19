from rest_framework import serializers

from apps.sync.models import SyncJob


class ImportJobCreateSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=("vndb",))
    external_id = serializers.RegexField(r"^v[1-9][0-9]*$")
    include_related = serializers.BooleanField(default=True, required=False)


class ImportJobQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SyncJob.Status.choices, required=False)
    provider = serializers.ChoiceField(choices=("vndb",), required=False)


class ImportJobProgressSerializer(serializers.Serializer):
    current_label = serializers.CharField(allow_blank=True)
    total = serializers.IntegerField(min_value=0)
    processed = serializers.IntegerField(min_value=0)
    synced = serializers.IntegerField(min_value=0)
    skipped = serializers.IntegerField(min_value=0)
    failed = serializers.IntegerField(min_value=0)


class ImportJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=("bangumi", "vndb"))
    external_id = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=SyncJob.Status.choices)
    parameters = serializers.JSONField()
    result = serializers.JSONField()
    error = serializers.CharField(allow_null=True)
    progress = ImportJobProgressSerializer()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField()
