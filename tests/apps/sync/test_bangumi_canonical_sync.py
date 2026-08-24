from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.index.models import (
    AiringEvent,
    Contributor,
    CurrentObservation,
    Entity,
    EntityRelation,
    EntityRelationEvidence,
    Observation,
    ProviderRecord,
    VoicePerformance,
    Work,
)
from apps.index.selectors.current import (
    current_appearances,
    current_credits,
    current_entity_relations,
)
from apps.sync.providers.bangumi import BangumiAPIError, bangumi_client
from apps.sync.services.calendar_service import calendar_sync_service
from apps.sync.services.episode_service import episode_service
from apps.sync.services.relation_service import relation_service
from apps.users.models import User, UserSubject
from apps.users.services.profile.profile_service import ProfileService
from integrations.mcp.queries import get_public_entity

pytestmark = pytest.mark.django_db(transaction=True)


def _work_entity(*, source_id: str = "1", title: str = "Example Anime") -> Entity:
    del source_id, title
    entity = Entity.objects.create(
        kind=Entity.Kind.WORK,
        audience=Entity.Audience.GENERAL,
    )
    Work.objects.create(entity=entity, work_type=Work.WorkType.ANIME)
    return entity


def _contributor(source_id: str) -> Contributor:
    del source_id
    entity = Entity.objects.create(kind=Entity.Kind.CONTRIBUTOR)
    return Contributor.objects.create(entity=entity, kind=Contributor.Kind.PERSON)


def _character_entity(source_id: str) -> Entity:
    del source_id
    return Entity.objects.create(kind=Entity.Kind.CHARACTER)


def test_relation_import_projects_canonical_rows_and_retracts_only_bangumi() -> None:
    subject = _work_entity()
    target = _work_entity(source_id="2", title="Related Anime")
    staff_member = _contributor("10")
    actor = _contributor("30")
    character_entity = _character_entity("20")
    staff = {
        "id": 10,
        "relation": "Director",
    }
    character = {
        "id": 20,
        "relation": "Main",
        "actors": [{"id": 30, "name": "Actor"}],
    }

    with (
        patch.object(
            bangumi_client,
            "fetch_subject_subjects",
            side_effect=([{"id": 2, "relation": "Sequel"}], []),
        ),
        patch.object(
            bangumi_client,
            "fetch_subject_persons",
            side_effect=([staff], []),
        ),
        patch.object(
            bangumi_client,
            "fetch_subject_characters",
            side_effect=([character], []),
        ),
        patch(
            "apps.sync.services.relation_service.name_normalizer.normalize_name",
            side_effect=lambda value: value,
        ),
        patch(
            "apps.sync.services.relation_service.subject_service.provide_subject",
            side_effect=lambda value: subject if str(value) == "1" else target,
        ),
        patch(
            "apps.sync.services.relation_service.staff_service.provide_staff",
            side_effect=lambda value: staff_member if str(value) == "10" else actor,
        ),
        patch(
            "apps.sync.services.relation_service.character_service.provide_character",
            return_value=character_entity,
        ),
    ):
        relation_service.upsert_subject_relation(1)
        relation_service.upsert_staff_relation(1)
        relation_service.upsert_character_relation(1)

        assert current_entity_relations().filter(from_entity_id=subject.id).count() == 1
        assert current_credits().filter(work_id=subject.id).count() == 1
        assert current_appearances().filter(work_id=subject.id).count() == 1
        assert VoicePerformance.objects.count() == 1

        relation_service.upsert_subject_relation(1)
        relation_service.upsert_staff_relation(1)
        relation_service.upsert_character_relation(1)

    assert not current_entity_relations().filter(from_entity_id=subject.id).exists()
    assert not current_credits().filter(work_id=subject.id).exists()
    assert not current_appearances().filter(work_id=subject.id).exists()
    assert EntityRelationEvidence.objects.count() >= 1
    assert CurrentObservation.objects.filter(
        provider_record__namespace__slug="subject-relations",
    ).exists()


def test_episode_import_creates_canonical_entity_and_collection_observation() -> None:
    subject = _work_entity()
    response = {"data": [{"id": 100, "name": "Episode 1", "type": 0, "ep": "1"}]}

    with (
        patch.object(bangumi_client, "fetch_subject_episodes", return_value=response),
        patch(
            "apps.sync.services.episode_service.subject_service.provide_subject",
            return_value=subject,
        ),
    ):
        episode_service.sync_subject_episodes(1)

    episode_record = ProviderRecord.objects.get(
        namespace__slug="episode",
        external_id="100",
    )
    episode_entity = episode_record.representations.get(is_active=True).entity
    assert episode_entity.kind == Entity.Kind.EPISODE
    assert EntityRelation.objects.filter(
        from_entity_id=subject.id,
        to_entity_id=episode_entity.id,
        relation_type="has-episode",
    ).exists()
    assert Observation.objects.filter(
        provider_record__namespace__slug="subject-episodes"
    ).exists()
    response = APIClient().get(f"/api/v1/index/entities/{subject.id}/episodes/")
    assert response.status_code == 200
    assert response.json()["results"][0]["provenance"]["provider"] == "bangumi"


def test_calendar_import_creates_current_canonical_airing_event() -> None:
    subject = _work_entity()
    payload = [
        {
            "weekday": {"id": 2, "en": "Tuesday"},
            "items": [{"id": 1, "collection": {"doing": 42}}],
        }
    ]

    with (
        patch.object(bangumi_client, "fetch_calendar", return_value=payload),
        patch(
            "apps.sync.services.calendar_service.subject_service.upsert_subject",
            return_value=subject,
        ),
        patch(
            "apps.sync.services.calendar_service.calendar_image_service.cache_cover",
            return_value="",
        ),
    ):
        result = calendar_sync_service.sync_calendar(sync_subject_details=False)
        calendar_sync_service.sync_calendar(sync_subject_details=False)

    event = AiringEvent.objects.get()
    assert result["synced_subject_count"] == 1
    assert event.work_id == subject.id
    assert event.weekday == 2
    assert event.precision == AiringEvent.Precision.WEEKDAY
    assert event.observation.current_projections.filter(
        mapper="bangumi.calendar"
    ).exists()


def test_adult_episode_description_requires_confirmed_rest_preference() -> None:
    subject = _work_entity()
    Entity.objects.filter(pk=subject.id).update(audience=Entity.Audience.ADULT)
    subject.refresh_from_db()
    response = {
        "data": [
            {
                "id": 100,
                "name": "Episode 1",
                "name_cn": "第一集",
                "type": 0,
                "ep": "1",
                "desc": "Adult episode description",
            }
        ]
    }
    with (
        patch.object(bangumi_client, "fetch_subject_episodes", return_value=response),
        patch(
            "apps.sync.services.episode_service.subject_service.provide_subject",
            return_value=subject,
        ),
    ):
        episode_service.sync_subject_episodes(1)

    episode_record = ProviderRecord.objects.get(
        namespace__slug="episode",
        external_id="100",
    )
    episode_entity = episode_record.representations.get(is_active=True).entity
    endpoint = f"/api/v1/index/entities/{subject.id}/episodes/"
    client = APIClient()
    anonymous = client.get(endpoint)
    user = User.objects.create_user(email="adult-episodes@example.test")
    client.force_authenticate(user)
    default_authenticated = client.get(endpoint)
    profile = ProfileService.get_or_create_profile(user=user)
    profile.show_adult_content = True
    profile.adult_content_confirmed_at = timezone.now()
    profile.save(update_fields=["show_adult_content", "adult_content_confirmed_at"])
    confirmed = client.get(endpoint)

    assert episode_entity.audience == Entity.Audience.ADULT
    assert anonymous.json()["results"][0]["description"] == ""
    assert default_authenticated.json()["results"][0]["description"] == ""
    assert confirmed.json()["results"][0]["title"] == "Episode 1"
    assert confirmed.json()["results"][0]["title_cn"] == "第一集"
    assert confirmed.json()["results"][0]["description"] == "Adult episode description"
    assert get_public_entity(entity_id=episode_entity.id)["descriptions"] == []


def test_episode_pagination_failure_does_not_persist_partial_results() -> None:
    first_page = {
        "data": [
            {"id": index + 1, "name": f"Episode {index + 1}", "type": 0}
            for index in range(100)
        ]
    }

    with (
        patch.object(
            bangumi_client,
            "fetch_subject_episodes",
            side_effect=(first_page, BangumiAPIError("provider unavailable")),
        ),
        patch(
            "apps.sync.services.episode_service.subject_service.provide_subject"
        ) as provide_subject,
        pytest.raises(BangumiAPIError, match="provider unavailable"),
    ):
        episode_service.sync_subject_episodes(1)

    provide_subject.assert_not_called()
    assert Entity.objects.filter(kind=Entity.Kind.EPISODE).count() == 0
    assert not ProviderRecord.objects.filter(
        namespace__slug="subject-episodes"
    ).exists()


def test_empty_episode_snapshot_retracts_current_links_without_deleting_history() -> (
    None
):
    subject = _work_entity()
    responses = (
        {"data": [{"id": 100, "name": "Episode 1", "type": 0, "ep": "1"}]},
        {"data": []},
    )

    with (
        patch.object(bangumi_client, "fetch_subject_episodes", side_effect=responses),
        patch(
            "apps.sync.services.episode_service.subject_service.provide_subject",
            return_value=subject,
        ),
    ):
        episode_service.sync_subject_episodes(1)
        user = User.objects.create_user(email="episodes@example.test")
        UserSubject.objects.create(
            user=user,
            entity_id=subject.id,
            status=UserSubject.Status.DOING,
        )
        assert (
            current_entity_relations()
            .filter(
                from_entity_id=subject.id,
                relation_type="has-episode",
            )
            .count()
            == 1
        )
        assert (
            APIClient()
            .get(f"/api/v1/index/entities/{subject.id}/episodes/")
            .json()["count"]
            == 1
        )
        episode_service.sync_subject_episodes(1)

    assert (
        not current_entity_relations()
        .filter(
            from_entity_id=subject.id,
            relation_type="has-episode",
        )
        .exists()
    )
    assert (
        EntityRelation.objects.filter(
            from_entity_id=subject.id,
            relation_type="has-episode",
        ).count()
        == 1
    )
    response = APIClient().get(f"/api/v1/index/entities/{subject.id}/episodes/")
    assert response.status_code == 200
    assert response.json()["count"] == 0
    assert (
        EntityRelationEvidence.objects.filter(
            relation__from_entity_id=subject.id,
            relation__relation_type="has-episode",
        ).count()
        == 1
    )
