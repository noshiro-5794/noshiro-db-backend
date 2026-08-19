import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.index.models import AiringEvent, Entity, Work
from apps.users.models import User
from apps.users.services.profile.profile_service import ProfileService

from .projection_fixtures import observation

pytestmark = pytest.mark.django_db


def test_calendar_returns_only_current_safe_events_with_provenance() -> None:
    safe_entity = Entity.objects.create(
        kind=Entity.Kind.WORK,
        audience=Entity.Audience.GENERAL,
    )
    adult_entity = Entity.objects.create(
        kind=Entity.Kind.WORK,
        audience=Entity.Audience.ADULT,
    )
    safe_work = Work.objects.create(
        entity=safe_entity,
        work_type=Work.WorkType.ANIME,
    )
    adult_work = Work.objects.create(
        entity=adult_entity,
        work_type=Work.WorkType.ANIME,
    )
    old = observation({"version": "calendar-old"})
    AiringEvent.objects.create(
        work=safe_work,
        weekday=1,
        precision=AiringEvent.Precision.WEEKDAY,
        raw_value="Monday",
        observation=old,
    )
    current = observation({"version": "calendar-current"})
    safe_event = AiringEvent.objects.create(
        work=safe_work,
        weekday=2,
        precision=AiringEvent.Precision.WEEKDAY,
        raw_value="Tuesday",
        observation=current,
    )
    AiringEvent.objects.create(
        work=adult_work,
        weekday=2,
        precision=AiringEvent.Precision.WEEKDAY,
        raw_value="Tuesday",
        observation=current,
    )
    endpoint = "/api/v1/index/calendar/events/"
    client = APIClient()

    anonymous = client.get(endpoint)
    assert anonymous.status_code == 200
    assert [item["id"] for item in anonymous.json()] == [safe_event.id]
    assert anonymous.json()[0]["provenance"]["observation_id"] == str(current.id)

    user = User.objects.create_user(email="calendar-adult@example.com")
    client.force_authenticate(user)
    profile = ProfileService.get_or_create_profile(user=user)
    profile.show_adult_content = True
    profile.adult_content_confirmed_at = timezone.now()
    profile.save(update_fields=["show_adult_content", "adult_content_confirmed_at"])

    confirmed = client.get(endpoint)
    assert {item["work_id"] for item in confirmed.json()} == {
        str(safe_entity.id),
        str(adult_entity.id),
    }
