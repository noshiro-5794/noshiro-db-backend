from io import StringIO

import pytest
from django.core.management import call_command

from apps.index.models import (
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRevision,
)
from apps.sync.providers.anilist import (
    ANILIST_EPISODE_NAMESPACE,
    ANILIST_STAFF_NAMESPACE,
)
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.providers.mal import MAL_ANIME_NAMESPACE
from apps.sync.services.provider_raw_policy import (
    raw_state_for_namespace,
    stub_state_for_namespace,
)
from apps.sync.services.provider_raw_state_service import (
    provider_raw_state_service,
)
from apps.sync.services.source_record_service import source_record_service

pytestmark = pytest.mark.django_db(transaction=True)


def _record(
    *,
    provider_slug: str,
    namespace_slug: str,
    external_id: str,
    schema_version: str | None = None,
) -> ProviderRecord:
    provider, _ = Provider.objects.get_or_create(
        slug=provider_slug,
        defaults={"name": provider_slug.title()},
    )
    namespace, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug=namespace_slug,
        defaults={"resource_type": ProviderNamespace.ResourceType.SUBJECT},
    )
    record = ProviderRecord.objects.create(
        namespace=namespace,
        external_id=external_id,
        origin="api",
        status="active",
    )
    if schema_version is not None:
        revision = ProviderRevision.objects.create(
            record=record,
            payload={"id": external_id},
            payload_hash=f"hash-{external_id}",
            schema_version=schema_version,
        )
        ProviderRecord.objects.filter(pk=record.pk).update(latest_revision=revision)
        record.refresh_from_db()
    return record


def test_policy_classifies_slim_and_legacy_namespaces() -> None:
    assert (
        raw_state_for_namespace(provider_slug="anilist", namespace_slug="episode")
        == ProviderRecord.RawState.SLIM
    )
    assert (
        raw_state_for_namespace(provider_slug="mal", namespace_slug="anime")
        == ProviderRecord.RawState.RAW
    )
    assert stub_state_for_namespace(provider_slug="bangumi") == (
        ProviderRecord.RawState.LEGACY
    )
    assert stub_state_for_namespace(provider_slug="anilist") == (
        ProviderRecord.RawState.STUB
    )


def test_classification_updates_dry_run_and_apply() -> None:
    bangumi_legacy = _record(
        provider_slug="bangumi",
        namespace_slug="subject",
        external_id="1",
    )
    anilist_stub = _record(
        provider_slug="anilist",
        namespace_slug="staff",
        external_id="2",
    )
    anilist_slim = _record(
        provider_slug="anilist",
        namespace_slug="episode",
        external_id="3",
        schema_version="anilist-graphql",
    )
    mal_raw = _record(
        provider_slug="mal",
        namespace_slug="anime",
        external_id="4",
        schema_version="mal-api-v2",
    )

    dry_run = provider_raw_state_service.classify(apply=False)

    assert dry_run["rules"]["bangumi_no_payload"]["count"] == 1
    bangumi_legacy.refresh_from_db()
    assert bangumi_legacy.raw_state == ProviderRecord.RawState.RAW

    provider_raw_state_service.classify(apply=True)

    bangumi_legacy.refresh_from_db()
    anilist_stub.refresh_from_db()
    anilist_slim.refresh_from_db()
    mal_raw.refresh_from_db()
    assert bangumi_legacy.raw_state == ProviderRecord.RawState.LEGACY
    assert anilist_stub.raw_state == ProviderRecord.RawState.STUB
    assert anilist_slim.raw_state == ProviderRecord.RawState.SLIM
    assert mal_raw.raw_state == ProviderRecord.RawState.RAW


def test_repair_mal_legacy_marks_stale_jikan_record_missing() -> None:
    record = _record(
        provider_slug="mal",
        namespace_slug="schedule-item",
        external_id="62973",
        schema_version="jikan-v4",
    )

    result = provider_raw_state_service.repair_mal_legacy(apply=True)

    assert result["updated"] == 1
    record.refresh_from_db()
    assert record.status == ProviderRecord.Status.MISSING
    assert record.raw_state == ProviderRecord.RawState.LEGACY


def test_audit_provider_raw_command_reports_json() -> None:
    _record(provider_slug="anilist", namespace_slug="staff", external_id="9")

    out = StringIO()
    call_command("audit_provider_raw", stdout=out)

    assert '"classification"' in out.getvalue()


def test_source_record_service_marks_raw_state_on_write() -> None:
    slim = source_record_service.record(
        namespace_spec=ANILIST_EPISODE_NAMESPACE,
        fetched=FetchedSourceRecord(
            external_id="ep-1",
            payload={"id": 1},
            schema_version="anilist-graphql",
            mapper_version="anilist-episode-v1",
        ),
    )
    raw = source_record_service.record(
        namespace_spec=MAL_ANIME_NAMESPACE,
        fetched=FetchedSourceRecord(
            external_id="5114",
            payload={"id": 5114, "title": "Test"},
            schema_version="mal-api-v2",
            mapper_version="mal-anime-v2",
        ),
    )
    stub = source_record_service.ensure_record(
        namespace_spec=ANILIST_STAFF_NAMESPACE,
        external_id="1",
        origin="api",
    )

    assert slim.record.raw_state == ProviderRecord.RawState.SLIM
    assert raw.record.raw_state == ProviderRecord.RawState.RAW
    assert stub.raw_state == ProviderRecord.RawState.STUB
