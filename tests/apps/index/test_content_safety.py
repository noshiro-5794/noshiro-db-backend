import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.index.models import (
    ContentSafety,
    Entity,
    EntityDescription,
    EntityMedia,
    EntityName,
    Fact,
    MediaAsset,
    Predicate,
    Work,
)
from apps.index.services import knowledge_ingestion_service
from apps.users.models import User
from apps.users.services.profile.profile_service import ProfileService
from integrations.mcp.queries import get_public_entity

from .projection_fixtures import observation

pytestmark = pytest.mark.django_db


def _enable_adult_content(*, user: User) -> None:
    profile = ProfileService.get_or_create_profile(user=user)
    profile.show_adult_content = True
    profile.adult_content_confirmed_at = timezone.now()
    profile.save(update_fields=["show_adult_content", "adult_content_confirmed_at"])


def test_adult_projection_requires_authenticated_confirmed_preference() -> None:
    entity = Entity.objects.create(
        kind=Entity.Kind.WORK,
        audience=Entity.Audience.ADULT,
    )
    Work.objects.create(entity=entity, work_type=Work.WorkType.GALGAME)
    current = observation({"version": "adult"})
    asset = MediaAsset.objects.create(
        url="https://provider.example.test/adult.jpg",
        provider_record=current.provider_record,
        media_type="image",
        safety=MediaAsset.Safety.EXPLICIT,
    )
    EntityName.objects.create(
        entity=entity,
        text="Adult title",
        kind=EntityName.Kind.ORIGINAL,
        provider_record=current.provider_record,
        observation=current,
    )
    EntityDescription.objects.create(
        entity=entity,
        text="Adult description",
        provider_record=current.provider_record,
        observation=current,
    )
    EntityMedia.objects.create(
        entity=entity,
        asset=asset,
        purpose="poster",
        observation=current,
    )
    user = User.objects.create_user(email="adult-reader@example.com")
    client = APIClient()
    endpoint = f"/api/v1/index/entities/{entity.id}/"

    anonymous = client.get(endpoint)
    client.force_authenticate(user)
    default_authenticated = client.get(endpoint)
    _enable_adult_content(user=user)
    confirmed = client.get(endpoint)

    assert anonymous.status_code == 200
    assert anonymous.json()["descriptions"] == []
    assert anonymous.json()["media"] == []
    assert default_authenticated.json()["descriptions"] == []
    assert default_authenticated.json()["media"] == []
    assert [item["text"] for item in confirmed.json()["descriptions"]] == [
        "Adult description"
    ]
    assert [item["url"] for item in confirmed.json()["media"]] == [
        "https://provider.example.test/adult.jpg"
    ]

    mcp_detail = get_public_entity(entity_id=entity.id)
    assert mcp_detail["descriptions"] == []
    assert mcp_detail["media"] == []


def test_field_level_safety_filters_descriptions_and_facts_with_provenance() -> None:
    entity = Entity.objects.create(
        kind=Entity.Kind.WORK,
        audience=Entity.Audience.GENERAL,
    )
    Work.objects.create(entity=entity, work_type=Work.WorkType.GALGAME)
    current = observation({"version": "field-safety"})
    EntityName.objects.create(
        entity=entity,
        text="Mixed safety title",
        kind=EntityName.Kind.ORIGINAL,
        provider_record=current.provider_record,
        observation=current,
    )
    EntityDescription.objects.create(
        entity=entity,
        text="Safe description",
        language="en",
        safety=ContentSafety.SAFE,
        provider_record=current.provider_record,
        observation=current,
    )
    EntityDescription.objects.create(
        entity=entity,
        text="Explicit description",
        language="ja",
        safety=ContentSafety.EXPLICIT,
        provider_record=current.provider_record,
        observation=current,
    )
    knowledge_ingestion_service.record_fact(
        entity=entity,
        observation=current,
        slug="safe-field",
        name="Safe Field",
        value="safe value",
        value_type=Predicate.ValueType.STRING,
        json_pointer="/safe_field",
        safety=ContentSafety.SAFE,
    )
    knowledge_ingestion_service.record_fact(
        entity=entity,
        observation=current,
        slug="explicit-field",
        name="Explicit Field",
        value="explicit value",
        value_type=Predicate.ValueType.STRING,
        json_pointer="/explicit_field",
        safety=ContentSafety.EXPLICIT,
    )
    user = User.objects.create_user(email="field-safety@example.com")
    client = APIClient()
    endpoint = f"/api/v1/index/entities/{entity.id}/"

    anonymous = client.get(endpoint).json()
    client.force_authenticate(user)
    default_authenticated = client.get(endpoint).json()
    _enable_adult_content(user=user)
    confirmed = client.get(endpoint).json()
    mcp_detail = get_public_entity(entity_id=entity.id)

    assert [item["text"] for item in anonymous["descriptions"]] == ["Safe description"]
    assert [item["predicate"] for item in anonymous["facts"]] == ["safe-field"]
    assert default_authenticated["descriptions"] == anonymous["descriptions"]
    assert default_authenticated["facts"] == anonymous["facts"]
    assert {item["text"] for item in confirmed["descriptions"]} == {
        "Safe description",
        "Explicit description",
    }
    assert {item["predicate"] for item in confirmed["facts"]} == {
        "safe-field",
        "explicit-field",
    }
    assert [item["text"] for item in mcp_detail["descriptions"]] == ["Safe description"]
    assert [item["predicate"] for item in mcp_detail["facts"]] == ["safe-field"]

    evidence = confirmed["facts"][0]["evidence"][0]
    assert evidence["provider"] == "projection-test"
    assert evidence["revision_id"] == str(current.mapping_run.revision_id)
    assert evidence["observation_id"] == str(current.id)
    assert evidence["json_pointer"] in {"/safe_field", "/explicit_field"}
    assert Fact.objects.filter(entity=entity).count() == 2
