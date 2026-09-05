import uuid

import pytest

from apps.index.models import (
    Entity,
    EntityName,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
    Work,
)
from apps.index.services import provider_candidate_service

pytestmark = pytest.mark.django_db(transaction=True)


def _entity(
    *,
    provider_slug: str,
    namespace_slug: str,
    external_id: str,
    name: str,
    make_work: bool = False,
) -> Entity:
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
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    ProviderRepresentation.objects.create(
        provider_record=record,
        entity=entity,
        mapping_kind=ProviderRepresentation.MappingKind.EXTERNAL_ID,
        method=ProviderRepresentation.Method.EXTERNAL_ID,
    )
    EntityName.objects.create(
        entity=entity,
        text=name,
        language="ja",
        kind=EntityName.Kind.ORIGINAL,
    )
    if make_work:
        Work.objects.create(entity=entity, work_type=Work.WorkType.ANIME)
    return entity


def test_exact_title_match_creates_candidate_with_evidence() -> None:
    _entity(
        provider_slug="anilist",
        namespace_slug="anime",
        external_id="10",
        name="Mushoku Tensei 3",
    )
    _entity(
        provider_slug="bangumi",
        namespace_slug="subject",
        external_id="100",
        name="Mushoku Tensei 3",
        make_work=True,
    )

    summary = provider_candidate_service.generate_candidates(
        min_similarity=0.6, top_k=5
    )

    assert summary["candidates_created"] == 1
    assert summary["anilist_entities"] == 1
    from apps.index.models import MatchCandidate, MatchEvidence

    row = MatchCandidate.objects.select_related("left_entity", "right_entity").get()
    assert float(row.score) >= 0.99
    evidence = MatchEvidence.objects.get(
        candidate=row, evidence_type="title_similarity"
    )
    assert evidence.value["similarity"] >= 0.99


def test_unrelated_titles_are_filtered_by_threshold() -> None:
    _entity(
        provider_slug="anilist",
        namespace_slug="anime",
        external_id="11",
        name="Totally Different Show",
    )
    _entity(
        provider_slug="bangumi",
        namespace_slug="subject",
        external_id="101",
        name="Unrelated Work Title",
        make_work=True,
    )

    summary = provider_candidate_service.generate_candidates(
        min_similarity=0.6, top_k=5
    )

    assert summary["candidates_created"] == 0
    assert summary["pairs"] == []


def test_candidate_generation_is_idempotent() -> None:
    _entity(
        provider_slug="anilist",
        namespace_slug="anime",
        external_id="12",
        name="Re Zero 4th Season",
    )
    _entity(
        provider_slug="bangumi",
        namespace_slug="subject",
        external_id="102",
        name="Re Zero 4th Season",
        make_work=True,
    )

    first = provider_candidate_service.generate_candidates(min_similarity=0.6, top_k=5)
    second = provider_candidate_service.generate_candidates(min_similarity=0.6, top_k=5)

    assert first["candidates_created"] == 1
    assert second["candidates_created"] == 0


def test_dry_run_reports_pairs_without_writing() -> None:
    _entity(
        provider_slug="anilist",
        namespace_slug="anime",
        external_id="13",
        name="A Shared Title",
    )
    _entity(
        provider_slug="bangumi",
        namespace_slug="subject",
        external_id="103",
        name="A Shared Title",
        make_work=True,
    )

    summary = provider_candidate_service.generate_candidates(
        min_similarity=0.6, top_k=5, create=False
    )

    assert summary["candidates_created"] == 0
    assert len(summary["pairs"]) == 1
    assert str(uuid.UUID(summary["pairs"][0]["source_entity"]))
