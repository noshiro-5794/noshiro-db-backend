import pytest
from rest_framework.test import APIClient

from apps.index.models import (
    Appearance,
    ContentRating,
    Contributor,
    Credit,
    Entity,
    EntityDescription,
    EntityMedia,
    EntityName,
    EntityRelation,
    EntityRelationEvidence,
    ExternalLink,
    MediaAsset,
    ProviderRepresentation,
    Release,
    ReleaseWork,
    ReleaseWorkEvidence,
    Work,
)
from apps.index.selectors.current import (
    current_content_ratings,
    current_external_links,
)
from integrations.mcp.queries import (
    get_public_entity,
    get_public_relations,
    search_public_entities,
)

from .projection_fixtures import observation

pytestmark = pytest.mark.django_db


def test_rest_and_mcp_return_only_current_supported_projections() -> None:
    work_entity = Entity.objects.create(kind=Entity.Kind.WORK)
    work = Work.objects.create(entity=work_entity, work_type=Work.WorkType.GALGAME)
    old_target = Entity.objects.create(kind=Entity.Kind.WORK)
    current_target = Entity.objects.create(kind=Entity.Kind.WORK)
    old_contributor = Contributor.objects.create(
        entity=Entity.objects.create(kind=Entity.Kind.CONTRIBUTOR)
    )
    current_contributor = Contributor.objects.create(
        entity=Entity.objects.create(kind=Entity.Kind.CONTRIBUTOR)
    )
    old_character = Entity.objects.create(kind=Entity.Kind.CHARACTER)
    current_character = Entity.objects.create(kind=Entity.Kind.CHARACTER)
    old_release = Release.objects.create(
        entity=Entity.objects.create(kind=Entity.Kind.RELEASE)
    )
    current_release = Release.objects.create(
        entity=Entity.objects.create(kind=Entity.Kind.RELEASE)
    )

    old_observation = observation({"version": 1})
    old_relation = EntityRelation.objects.create(
        from_entity=work_entity,
        to_entity=old_target,
        relation_type="sequel",
    )
    EntityRelationEvidence.objects.create(
        relation=old_relation,
        observation=old_observation,
        json_pointer="/relations/0",
    )
    Credit.objects.create(
        work=work,
        contributor=old_contributor,
        role="writer",
        observation=old_observation,
    )
    Appearance.objects.create(
        work=work,
        character_entity=old_character,
        role="main",
        observation=old_observation,
    )
    old_release_link = ReleaseWork.objects.create(
        release=old_release,
        work=work,
        role=ReleaseWork.Role.PRIMARY,
    )
    ReleaseWorkEvidence.objects.create(
        release_work=old_release_link,
        observation=old_observation,
        json_pointer="/releases/0",
    )

    current_observation = observation({"version": 2})
    current_relation = EntityRelation.objects.create(
        from_entity=work_entity,
        to_entity=current_target,
        relation_type="prequel",
    )
    EntityRelationEvidence.objects.create(
        relation=current_relation,
        observation=current_observation,
        json_pointer="/relations/0",
    )
    Credit.objects.create(
        work=work,
        contributor=current_contributor,
        role="director",
        observation=current_observation,
    )
    Appearance.objects.create(
        work=work,
        character_entity=current_character,
        role="supporting",
        observation=current_observation,
    )
    current_release_link = ReleaseWork.objects.create(
        release=current_release,
        work=work,
        role=ReleaseWork.Role.PRIMARY,
    )
    ReleaseWorkEvidence.objects.create(
        release_work=current_release_link,
        observation=current_observation,
        json_pointer="/releases/0",
    )

    client = APIClient()
    base = f"/api/v1/index/entities/{work_entity.id}"
    relations = client.get(f"{base}/relations/")
    credits = client.get(f"{base}/credits/")
    characters = client.get(f"{base}/characters/")
    releases = client.get(f"{base}/releases/")
    mcp_relations = get_public_relations(entity_id=work_entity.id)

    assert relations.status_code == 200
    assert [item["target"]["id"] for item in relations.json()] == [
        str(current_target.id)
    ]
    assert relations.json()[0]["evidence"][0]["observation_id"] == str(
        current_observation.id
    )
    assert credits.status_code == 200
    assert [item["contributor"]["id"] for item in credits.json()] == [
        str(current_contributor.entity_id)
    ]
    assert credits.json()[0]["provenance"]["observation_id"] == str(
        current_observation.id
    )
    assert characters.status_code == 200
    assert [item["character"]["id"] for item in characters.json()["results"]] == [
        str(current_character.id)
    ]
    assert characters.json()["results"][0]["provenance"]["observation_id"] == str(
        current_observation.id
    )
    assert releases.status_code == 200
    assert [item["release"]["id"] for item in releases.json()] == [
        str(current_release.entity_id)
    ]
    assert releases.json()[0]["evidence"][0]["observation_id"] == str(
        current_observation.id
    )
    assert [item["target"]["id"] for item in mcp_relations["results"]] == [
        str(current_target.id)
    ]


def test_field_projections_retract_without_deleting_history() -> None:
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    Work.objects.create(entity=entity, work_type=Work.WorkType.GALGAME)
    first = observation({"version": 1})
    old_asset = MediaAsset.objects.create(
        url="https://provider.example.test/old.jpg",
        provider_record=first.provider_record,
        media_type="image",
        safety=MediaAsset.Safety.SAFE,
    )
    EntityName.objects.create(
        entity=entity,
        text="Old title",
        kind=EntityName.Kind.ORIGINAL,
        provider_record=first.provider_record,
        observation=first,
    )
    EntityDescription.objects.create(
        entity=entity,
        text="Old description",
        provider_record=first.provider_record,
        observation=first,
    )
    EntityMedia.objects.create(
        entity=entity,
        asset=old_asset,
        purpose="poster",
        observation=first,
    )
    ExternalLink.objects.create(
        entity=entity,
        url="https://provider.example.test/old-link",
        provider_record=first.provider_record,
        observation=first,
    )
    ContentRating.objects.create(
        entity=entity,
        system="test",
        value="18",
        provider_record=first.provider_record,
        observation=first,
    )

    second = observation({"version": 2})
    current_asset = MediaAsset.objects.create(
        url="https://provider.example.test/current.jpg",
        provider_record=second.provider_record,
        media_type="image",
        safety=MediaAsset.Safety.SAFE,
    )
    EntityName.objects.create(
        entity=entity,
        text="Current title",
        kind=EntityName.Kind.ORIGINAL,
        provider_record=second.provider_record,
        observation=second,
    )
    EntityDescription.objects.create(
        entity=entity,
        text="Current description",
        provider_record=second.provider_record,
        observation=second,
    )
    EntityMedia.objects.create(
        entity=entity,
        asset=current_asset,
        purpose="poster",
        observation=second,
    )
    ExternalLink.objects.create(
        entity=entity,
        url="https://provider.example.test/current-link",
        provider_record=second.provider_record,
        observation=second,
    )
    ContentRating.objects.create(
        entity=entity,
        system="test",
        value="16",
        provider_record=second.provider_record,
        observation=second,
    )

    client = APIClient()
    detail = client.get(f"/api/v1/index/entities/{entity.id}/")
    mcp_detail = get_public_entity(entity_id=entity.id)

    assert detail.status_code == 200
    assert [item["text"] for item in detail.json()["names"]] == ["Current title"]
    assert [item["text"] for item in detail.json()["descriptions"]] == [
        "Current description"
    ]
    assert [item["url"] for item in detail.json()["media"]] == [
        "https://provider.example.test/current.jpg"
    ]
    assert detail.json()["names"][0]["provenance"] == {
        "provider": "projection-test",
        "namespace": "work-relations",
        "external_id": "work-1",
        "observation_id": str(second.id),
        "revision_id": str(second.mapping_run.revision_id),
        "observed_at": second.observed_at.isoformat().replace("+00:00", "Z"),
    }
    assert detail.json()["descriptions"][0]["is_reviewed"] is False
    assert detail.json()["media"][0]["provenance"]["observation_id"] == str(second.id)
    assert [item["url"] for item in detail.json()["external_links"]] == [
        "https://provider.example.test/current-link"
    ]
    assert detail.json()["content_ratings"] == [
        {
            "system": "test",
            "value": "16",
            "region": "",
            "minimum_age": None,
            "provenance": detail.json()["content_ratings"][0]["provenance"],
        }
    ]
    assert detail.json()["content_ratings"][0]["provenance"]["observation_id"] == str(
        second.id
    )
    assert mcp_detail["display_name"] == "Current title"
    assert search_public_entities(query="Old title")["results"] == []
    assert [
        item["id"] for item in search_public_entities(query="Current title")["results"]
    ] == [str(entity.id)]
    assert list(current_external_links().values_list("url", flat=True)) == [
        "https://provider.example.test/current-link"
    ]
    assert list(current_content_ratings().values_list("value", flat=True)) == ["16"]

    observation({"version": 3, "fields": []})

    retracted = client.get(f"/api/v1/index/entities/{entity.id}/")
    retracted_mcp = get_public_entity(entity_id=entity.id)
    assert retracted.status_code == 200
    assert retracted.json()["display_name"] == "Untitled"
    assert retracted.json()["names"] == []
    assert retracted.json()["descriptions"] == []
    assert retracted.json()["media"] == []
    assert retracted.json()["external_links"] == []
    assert retracted.json()["content_ratings"] == []
    assert retracted_mcp["display_name"] == "Untitled"
    assert search_public_entities(query="Current title")["results"] == []
    assert not current_external_links().exists()
    assert not current_content_ratings().exists()
    assert EntityName.objects.filter(entity=entity).count() == 2
    assert EntityDescription.objects.filter(entity=entity).count() == 2
    assert EntityMedia.objects.filter(entity=entity).count() == 2
    assert ExternalLink.objects.filter(entity=entity).count() == 2
    assert ContentRating.objects.filter(entity=entity).count() == 2


def test_forbidden_redistribution_provider_is_excluded_from_public_projection() -> None:
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    Work.objects.create(entity=entity, work_type=Work.WorkType.GALGAME)
    current = observation({"version": "redistribution-forbidden"})
    provider = current.provider_record.namespace.provider
    provider.redistribution_policy = provider.UsagePolicy.FORBIDDEN
    provider.save(update_fields=["redistribution_policy", "updated_at"])
    ProviderRepresentation.objects.create(
        provider_record=current.provider_record,
        entity=entity,
        mapping_kind=ProviderRepresentation.MappingKind.EXACT,
        method=ProviderRepresentation.Method.PROVIDER,
    )
    EntityName.objects.create(
        entity=entity,
        text="Restricted provider title",
        provider_record=current.provider_record,
        observation=current,
    )

    client = APIClient()
    detail = client.get(f"/api/v1/index/entities/{entity.id}/")
    evidence = client.get(f"/api/v1/index/entities/{entity.id}/evidence/")

    assert detail.status_code == 200
    assert detail.json()["names"] == []
    assert detail.json()["sources"] == []
    assert evidence.status_code == 200
    assert evidence.json() == []
