from copy import deepcopy
from unittest.mock import patch

import pytest
from django.db import connection

from apps.index.models import (
    Appearance,
    ContentRating,
    Contributor,
    Credit,
    CurrentObservation,
    Entity,
    EntityMedia,
    EntityName,
    EntityRelation,
    EntityRelationEvidence,
    EntityTerm,
    ExternalLink,
    Fact,
    MetricSnapshot,
    Observation,
    Organization,
    Person,
    ProviderRecord,
    ProviderRepresentation,
    ProviderRevision,
    Release,
    ReleaseWork,
    ReleaseWorkEvidence,
    Term,
    VoicePerformance,
    Work,
)
from apps.index.selectors.current import (
    current_appearances,
    current_credits,
    current_entity_relations,
    current_release_work_links,
)
from apps.index.services import knowledge_ingestion_service
from apps.sync.providers.contracts import (
    CatalogSourceSpec,
    FetchedSourceRecord,
    SourceNamespaceSpec,
)
from apps.sync.providers.vndb import VNDBAPIError, VNDBImportBatch
from apps.sync.services.source_record_service import source_record_service
from apps.sync.services.vndb_service import vndb_import_service

pytestmark = pytest.mark.django_db


def _batch() -> VNDBImportBatch:
    return VNDBImportBatch(
        work={
            "id": "v1",
            "title": "Example",
            "alttitle": "Example original",
            "olang": "ja",
            "released": "2020-01-02",
            "length_minutes": 600,
            "length_votes": 20,
            "devstatus": 0,
            "languages": ["ja", "en"],
            "platforms": ["win"],
            "rating": 82.5,
            "votecount": 100,
            "aliases": ["Example alias"],
            "titles": [
                {
                    "lang": "ja",
                    "title": "Example original",
                    "latin": "Example romanized",
                    "official": True,
                    "main": True,
                }
            ],
            "image": {
                "url": "https://example.test/poster.jpg",
                "sexual": 2.0,
                "violence": 0,
            },
            "screenshots": [
                {
                    "url": "https://example.test/screenshot.jpg",
                    "sexual": 0,
                    "violence": 0,
                }
            ],
            "extlinks": [
                {
                    "url": "https://example.test/work",
                    "label": "Official website",
                }
            ],
            "developers": [
                {
                    "id": "p1",
                    "name": "Example developer",
                    "original": "Developer original",
                    "type": "co",
                }
            ],
            "staff": [
                {
                    "id": "s1",
                    "aid": 10,
                    "name": "Example contributor alias",
                    "original": "Contributor original",
                    "lang": "ja",
                    "role": "scenario",
                    "note": "Main route",
                }
            ],
            "va": [
                {
                    "staff": {
                        "id": "s1",
                        "aid": 10,
                        "name": "Example contributor alias",
                        "original": "Contributor original",
                        "lang": "ja",
                    },
                    "character": {
                        "id": "c1",
                        "name": "Example character",
                        "original": "Character original",
                    },
                    "note": None,
                }
            ],
            "relations": [
                {
                    "id": "v2",
                    "title": "Related work",
                    "olang": "ja",
                    "relation": "seq",
                    "relation_official": True,
                }
            ],
            "tags": [
                {
                    "id": "g1",
                    "name": "Example tag",
                    "rating": 2.5,
                    "spoiler": 1,
                    "lie": False,
                }
            ],
        },
        releases=(
            {
                "id": "r1",
                "title": "Example release",
                "released": "2020-01-02",
                "platforms": ["win"],
                "official": True,
                "patch": False,
                "minage": 18,
                "languages": [{"lang": "ja", "title": "Example release"}],
                "vns": [{"id": "v1", "rtype": "complete"}],
                "producers": [
                    {
                        "id": "p1",
                        "name": "Example developer",
                        "developer": True,
                        "publisher": True,
                    }
                ],
                "extlinks": [
                    {
                        "url": "https://example.test/release",
                        "label": "Store",
                    }
                ],
            },
        ),
        characters=(
            {
                "id": "c1",
                "name": "Example character",
                "original": "Character original",
                "birthday": [1, 2],
                "height": 160,
                "sex": ["f", "m"],
                "vns": [{"id": "v1", "role": "main", "spoiler": 1}],
                "traits": [
                    {
                        "id": "i1",
                        "name": "Example trait",
                        "group_id": "i100",
                        "group_name": "Personality",
                        "spoiler": 2,
                        "lie": False,
                    }
                ],
            },
        ),
        contributors=(
            {
                "id": "s1",
                "aid": 1,
                "ismain": True,
                "name": "Example contributor",
                "original": "Contributor original",
                "lang": "ja",
                "aliases": [
                    {
                        "aid": 10,
                        "name": "Example contributor alias",
                        "latin": "Contributor alias latin",
                        "ismain": False,
                    }
                ],
                "extlinks": [
                    {
                        "url": "https://example.test/contributor",
                        "label": "Official profile",
                    }
                ],
            },
        ),
        related_fetched=True,
    )


def test_vndb_fetch_completes_before_persistence_transaction_starts() -> None:
    baseline_atomic_depth = len(connection.atomic_blocks)

    def fetch(*_args, **_kwargs):
        assert len(connection.atomic_blocks) == baseline_atomic_depth
        return _batch()

    with (
        patch.object(vndb_import_service, "_persist_batch") as persist,
        patch(
            "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
            side_effect=fetch,
        ),
    ):
        vndb_import_service.import_work(vndb_id="v1")

    persist.assert_called_once()


def test_vndb_fetch_failure_writes_nothing() -> None:
    with (
        patch(
            "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
            side_effect=VNDBAPIError("provider unavailable"),
        ),
        pytest.raises(VNDBAPIError, match="provider unavailable"),
    ):
        vndb_import_service.import_work(vndb_id="v1")

    assert ProviderRecord.objects.count() == 0
    assert ProviderRevision.objects.count() == 0
    assert Entity.objects.count() == 0


def test_vndb_persistence_failure_rolls_back_complete_batch() -> None:
    with (
        patch(
            "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
            return_value=_batch(),
        ),
        patch.object(
            vndb_import_service,
            "_import_characters",
            side_effect=RuntimeError("projection failed"),
        ),
        pytest.raises(RuntimeError, match="projection failed"),
    ):
        vndb_import_service.import_work(vndb_id="v1")

    assert ProviderRecord.objects.count() == 0
    assert ProviderRevision.objects.count() == 0
    assert ProviderRepresentation.objects.count() == 0
    assert Entity.objects.count() == 0


def test_vndb_complete_batch_is_idempotent() -> None:
    with patch(
        "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
        return_value=_batch(),
    ):
        first = vndb_import_service.import_work(vndb_id="v1")
        second = vndb_import_service.import_work(vndb_id="v1")

    assert second.id == first.id
    assert Work.objects.count() == 2
    assert Release.objects.count() == 1
    assert Contributor.objects.count() == 2
    assert Person.objects.count() == 1
    assert Organization.objects.count() == 1
    assert Appearance.objects.count() == 1
    assert Credit.objects.count() == 2
    assert VoicePerformance.objects.count() == 1
    assert EntityRelation.objects.count() == 3
    assert EntityRelationEvidence.objects.count() == 3
    assert ReleaseWork.objects.get().role == ReleaseWork.Role.PRIMARY
    assert ContentRating.objects.get().observation is not None
    assert ReleaseWorkEvidence.objects.count() == 1
    assert ProviderRecord.objects.count() == 10
    assert ProviderRevision.objects.count() == 5
    assert ProviderRepresentation.objects.count() == 7
    assert MetricSnapshot.objects.count() == 2
    assert Observation.objects.count() == 5
    assert CurrentObservation.objects.count() == 5
    assert EntityTerm.objects.count() == 2
    assert Term.objects.filter(slug="i1", parent__slug="group-i100").exists()
    assert ExternalLink.objects.count() == 3
    assert EntityMedia.objects.count() == 2
    assert EntityName.objects.filter(kind=EntityName.Kind.ROMANIZED).exists()
    assert Fact.objects.filter(predicate__slug="release-period").exists()
    assert Fact.objects.filter(
        predicate__slug="character-actual-sex",
        spoiler_level=2,
    ).exists()


def test_new_revision_replaces_current_projection_without_deleting_history() -> None:
    first_batch = _batch()
    second_work = deepcopy(first_batch.work)
    second_work["title"] = "Revised Example"
    second_work["developers"] = []
    second_work["staff"] = []
    second_work["relations"] = []
    second_work["va"] = []
    second_batch = VNDBImportBatch(
        work=second_work,
        releases=(),
        characters=(),
        contributors=(),
        related_fetched=True,
    )

    with patch(
        "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
        side_effect=(first_batch, second_batch),
    ):
        entity = vndb_import_service.import_work(vndb_id="v1")
        vndb_import_service.import_work(vndb_id="v1")

    assert Observation.objects.filter(provider_record__external_id="v1").count() == 4
    assert Credit.objects.filter(work_id=entity.id).count() == 2
    assert EntityRelation.objects.filter(from_entity=entity).count() == 1
    assert Appearance.objects.filter(work_id=entity.id).count() == 1
    assert ReleaseWork.objects.filter(work_id=entity.id).count() == 1
    assert not current_credits().filter(work_id=entity.id).exists()
    assert not current_entity_relations().filter(from_entity=entity).exists()
    assert not current_appearances().filter(work_id=entity.id).exists()
    assert not current_release_work_links().filter(work_id=entity.id).exists()


def test_relation_survives_when_another_current_provider_observation_supports_it() -> (
    None
):
    batch = _batch()
    with patch(
        "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
        return_value=batch,
    ):
        entity = vndb_import_service.import_work(vndb_id="v1")

    relation = EntityRelation.objects.get(from_entity=entity)
    other_namespace = SourceNamespaceSpec(
        source=CatalogSourceSpec(
            slug="other-provider",
            name="Other Provider",
            base_url="https://other.example.test",
        ),
        slug="work",
        resource_type="subject",
    )
    other_recorded = source_record_service.record(
        namespace_spec=other_namespace,
        fetched=FetchedSourceRecord(
            external_id="v-other-support",
            payload={"relation": str(relation.id)},
            mapper_version="test-v1",
        ),
    )
    other_observation = knowledge_ingestion_service.record_observation(
        provider_record=other_recorded.record,
        mapper="test.relation",
        mapper_version="test-v1",
        normalized_data={"relation": str(relation.id)},
        schema_name="test.relation",
        schema_version="1",
    )
    EntityRelationEvidence.objects.create(
        relation=relation,
        observation=other_observation,
        json_pointer="/relation",
    )

    revised_work = deepcopy(batch.work)
    revised_work["title"] = "Revised Example"
    revised_work["relations"] = []
    with patch(
        "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
        return_value=VNDBImportBatch(work=revised_work),
    ):
        vndb_import_service.import_work(vndb_id="v1", include_related=False)

    assert current_entity_relations().filter(pk=relation.pk).exists()


def test_without_related_keeps_last_complete_related_projection() -> None:
    batch = _batch()
    with patch(
        "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
        return_value=batch,
    ):
        entity = vndb_import_service.import_work(vndb_id="v1")

    revised_work = deepcopy(batch.work)
    revised_work["title"] = "Revised without related data"
    with patch(
        "apps.sync.services.vndb_service.vndb_client.fetch_import_batch",
        return_value=VNDBImportBatch(work=revised_work, related_fetched=False),
    ):
        vndb_import_service.import_work(vndb_id="v1", include_related=False)

    assert current_release_work_links().filter(work_id=entity.id).count() == 1
    assert current_appearances().filter(work_id=entity.id).count() == 1


@pytest.mark.parametrize(
    ("raw", "start", "end", "precision"),
    [
        ("2020", "2020-01-01", "2020-12-31", Release.DatePrecision.YEAR),
        ("2020-02", "2020-02-01", "2020-02-29", Release.DatePrecision.MONTH),
        ("2020-02-03", "2020-02-03", "2020-02-03", Release.DatePrecision.DAY),
    ],
)
def test_vndb_partial_date_preserves_precision(raw, start, end, precision) -> None:
    parsed_start, parsed_end, parsed_precision = vndb_import_service._partial_date(raw)

    assert parsed_start.isoformat() == start
    assert parsed_end.isoformat() == end
    assert parsed_precision == precision
