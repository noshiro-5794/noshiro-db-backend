from rest_framework import serializers

from apps.sync.models import SyncJob
from apps.sync.services.import_providers import (
    import_provider_choices,
    import_provider_for,
)


class ImportJobCreateSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=import_provider_choices())
    external_id = serializers.CharField(max_length=255)
    include_related = serializers.BooleanField(default=True, required=False)

    def validate(self, attrs):
        provider = import_provider_for(attrs["provider"])
        if not provider.external_id_pattern.fullmatch(attrs["external_id"]):
            raise serializers.ValidationError(
                {"external_id": f"Invalid {provider.slug} external id."}
            )
        if "include_related" not in attrs:
            attrs["include_related"] = provider.default_include_related
        return attrs


class ImportJobQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SyncJob.Status.choices, required=False)
    provider = serializers.ChoiceField(
        choices=import_provider_choices(), required=False
    )


class ImportJobProgressSerializer(serializers.Serializer):
    current_label = serializers.CharField(allow_blank=True)
    total = serializers.IntegerField(min_value=0)
    processed = serializers.IntegerField(min_value=0)
    synced = serializers.IntegerField(min_value=0)
    skipped = serializers.IntegerField(min_value=0)
    failed = serializers.IntegerField(min_value=0)


class ImportJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=import_provider_choices())
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
