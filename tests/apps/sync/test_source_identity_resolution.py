import pytest

from apps.index.models import (
    Provider,
    ProviderRecord,
    ProviderRevision,
    SourceRecord,
    Subject,
    SubjectExternalIdentity,
)
from apps.sync.providers.bangumi import BANGUMI_SUBJECT_NAMESPACE
from apps.sync.providers.contracts import FetchedSourceRecord
from apps.sync.services.source_record_service import (
    SourceCatalogConflict,
    source_identity_service,
    source_record_service,
)

pytestmark = pytest.mark.django_db


def _subject(*, info_source: str, id_source: str) -> Subject:
    return Subject.objects.create(
        info_source=info_source,
        id_source=id_source,
        title=f"Subject {id_source}",
    )


def test_legacy_identity_is_used_only_before_namespace_backfill() -> None:
    subject = _subject(info_source="bangumi_subject", id_source="1")

    assert (
        source_identity_service.resolve_subject(
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            external_id="1",
            legacy_source="bangumi_subject",
        )
        == subject
    )


def test_inactive_identity_cannot_be_revived_by_legacy_fields() -> None:
    subject = _subject(info_source="bangumi_subject", id_source="2")
    record = source_record_service.ensure_record(
        namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
        external_id="2",
        origin=SourceRecord.Origin.API,
    )
    source_identity_service.bind_subject(
        subject=subject,
        source_record=record,
        match_method=SubjectExternalIdentity.MatchMethod.PROVIDER,
    )
    SourceRecord.objects.filter(pk=record.pk).update(status=SourceRecord.Status.DELETED)

    assert (
        source_identity_service.resolve_subject(
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            external_id="2",
            legacy_source="bangumi_subject",
        )
        is None
    )


def test_identity_and_legacy_target_conflict_is_rejected() -> None:
    _subject(info_source="bangumi_subject", id_source="3")
    canonical = _subject(info_source="manual", id_source="canonical-3")
    record = source_record_service.ensure_record(
        namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
        external_id="3",
        origin=SourceRecord.Origin.API,
    )
    source_identity_service.bind_subject(
        subject=canonical,
        source_record=record,
        match_method=SubjectExternalIdentity.MatchMethod.MANUAL,
    )

    with pytest.raises(SourceCatalogConflict):
        source_identity_service.resolve_subject(
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            external_id="3",
            legacy_source="bangumi_subject",
        )


def test_forbidden_storage_policy_rejects_payload_without_persisting_it() -> None:
    Provider.objects.create(
        slug=BANGUMI_SUBJECT_NAMESPACE.source.slug,
        name=BANGUMI_SUBJECT_NAMESPACE.source.name,
        storage_policy=Provider.UsagePolicy.FORBIDDEN,
    )

    with pytest.raises(SourceCatalogConflict, match="forbids source payload storage"):
        source_record_service.record(
            namespace_spec=BANGUMI_SUBJECT_NAMESPACE,
            fetched=FetchedSourceRecord(
                external_id="4",
                payload={"id": 4, "private": "must not be stored"},
            ),
        )

    assert not ProviderRecord.objects.exists()
    assert not ProviderRevision.objects.exists()
