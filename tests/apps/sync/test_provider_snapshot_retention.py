from io import StringIO

import pytest
from django.core.management import call_command

from apps.index.models import (
    CurrentObservation,
    MappingRun,
    Observation,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRevision,
)
from apps.sync.services.provider_snapshot_retention_service import (
    provider_snapshot_retention_service,
)

pytestmark = pytest.mark.django_db(transaction=True)


def _snapshot_record() -> tuple[ProviderRecord, ProviderRevision, Observation]:
    provider, _ = Provider.objects.get_or_create(slug="mal", defaults={"name": "MAL"})
    namespace, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug="season",
        defaults={"resource_type": ProviderNamespace.ResourceType.SCHEDULE},
    )
    record = ProviderRecord.objects.create(
        namespace=namespace,
        external_id="season-now:2026Q3",
        origin="api",
        status="active",
    )
    old_revision = ProviderRevision.objects.create(
        record=record,
        payload={"version": 1},
        payload_hash="old",
        schema_version="mal-api-v2",
    )
    old_run = MappingRun.objects.create(
        revision=old_revision,
        mapper="mal.season",
        mapper_version="mal-season-v2",
        status=MappingRun.Status.SUCCEEDED,
    )
    Observation.objects.create(
        provider_record=record,
        mapping_run=old_run,
        origin=Observation.Origin.MAPPED,
        schema_name="index.schedule",
        schema_version="2",
        normalized_data={"version": 1},
        normalized_hash="old",
    )
    latest_revision = ProviderRevision.objects.create(
        record=record,
        payload={"version": 2},
        payload_hash="latest",
        schema_version="mal-api-v2",
    )
    latest_run = MappingRun.objects.create(
        revision=latest_revision,
        mapper="mal.season",
        mapper_version="mal-season-v2",
        status=MappingRun.Status.SUCCEEDED,
    )
    latest_observation = Observation.objects.create(
        provider_record=record,
        mapping_run=latest_run,
        origin=Observation.Origin.MAPPED,
        schema_name="index.schedule",
        schema_version="2",
        normalized_data={"version": 2},
        normalized_hash="latest",
    )
    ProviderRecord.objects.filter(pk=record.pk).update(
        latest_revision=latest_revision,
        latest_payload_hash="latest",
    )
    CurrentObservation.objects.create(
        provider_record=record,
        mapper="mal.season",
        schema_name="index.schedule",
        observation=latest_observation,
    )
    record.refresh_from_db()
    return record, latest_revision, latest_observation


def test_retain_current_removes_older_snapshot_revisions() -> None:
    record, latest_revision, latest_observation = _snapshot_record()

    result = provider_snapshot_retention_service.retain_current(record)

    assert result["deleted_revisions"] == 1
    assert ProviderRevision.objects.filter(record=record).count() == 1
    assert ProviderRevision.objects.filter(record=record).get().pk == latest_revision.pk
    assert Observation.objects.filter(provider_record=record).count() == 1
    assert (
        Observation.objects.filter(provider_record=record).get().pk
        == latest_observation.pk
    )


def test_compact_command_reports_dry_run() -> None:
    _snapshot_record()

    out = StringIO()
    call_command("compact_provider_history", stdout=out)

    assert '"compactable_revisions": 1' in out.getvalue()
