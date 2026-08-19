from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.index.models import (
    Entity,
    EntityName,
    EntityRedirect,
    MatchCandidate,
    MatchDecision,
    MergeEvent,
    SplitEvent,
    Work,
)
from apps.index.services import EntityResolutionError, entity_resolution_service
from apps.users.models import User, UserSubject

pytestmark = pytest.mark.django_db(transaction=True)


def _work(name: str, *, visibility: str = Entity.Visibility.PUBLIC) -> Entity:
    entity = Entity.objects.create(
        kind=Entity.Kind.WORK,
        visibility=visibility,
    )
    Work.objects.create(entity=entity, work_type=Work.WorkType.GALGAME)
    EntityName.objects.create(
        entity=entity,
        text=name,
        kind=EntityName.Kind.OFFICIAL,
        is_official=True,
    )
    return entity


def _candidate(left: Entity, right: Entity) -> MatchCandidate:
    return MatchCandidate.objects.create(
        left_entity=left,
        right_entity=right,
        score="1.0000",
        runner_up_margin="1.0000",
        policy_version="resolution-test-v1",
    )


def test_bind_creates_reversible_redirect_and_combined_projection() -> None:
    canonical = _work("Canonical title")
    representation = _work("Provider title")
    Entity.objects.filter(pk=canonical.pk).update(
        created_at=timezone.now() - timedelta(days=1)
    )
    canonical.refresh_from_db()
    decision = entity_resolution_service.decide_candidate(
        candidate=_candidate(canonical, representation),
        outcome=MatchDecision.Outcome.BIND,
        decided_by="manual",
        reason="Verified cross-provider identity.",
    )

    representation.refresh_from_db()
    redirect = EntityRedirect.objects.get(is_active=True)
    merge_event = MergeEvent.objects.get(pk=decision.decision_data["merge_event_id"])
    assert redirect.source_entity_id == representation.pk
    assert redirect.target_entity_id == canonical.pk
    assert representation.lifecycle == Entity.Lifecycle.MERGED
    assert merge_event.snapshot["source_cluster_ids"] == [str(representation.pk)]

    client = APIClient()
    canonical_response = client.get(f"/api/v1/index/entities/{canonical.pk}/")
    redirected_response = client.get(f"/api/v1/index/entities/{representation.pk}/")

    assert canonical_response.status_code == 200
    assert redirected_response.status_code == 200
    assert canonical_response.json() == redirected_response.json()
    assert {row["text"] for row in canonical_response.json()["names"]} == {
        "Canonical title",
        "Provider title",
    }

    split = entity_resolution_service.split(
        merge_event=merge_event,
        reason="Provider records refer to different editions.",
    )
    representation.refresh_from_db()
    redirect.refresh_from_db()
    assert isinstance(split, SplitEvent)
    assert representation.lifecycle == Entity.Lifecycle.ACTIVE
    assert not redirect.is_active
    assert entity_resolution_service.resolve(representation) == representation
    assert {
        row["text"]
        for row in client.get(f"/api/v1/index/entities/{representation.pk}/").json()[
            "names"
        ]
    } == {"Provider title"}

    second_merge = entity_resolution_service.merge(
        source=representation,
        target=canonical,
        method=MergeEvent.Method.MANUAL,
        reason="Corrected after further verification.",
    )
    assert second_merge.pk != merge_event.pk
    assert (
        EntityRedirect.objects.filter(
            source_entity=representation, is_active=True
        ).count()
        == 1
    )
    assert EntityRedirect.objects.filter(source_entity=representation).count() == 2


def test_bind_abstains_from_conflicting_user_library_data() -> None:
    left = _work("Left")
    right = _work("Right")
    user = User.objects.create_user(email="conflict@example.com")
    UserSubject.objects.create(user=user, entity=left, status=UserSubject.Status.DOING)
    UserSubject.objects.create(user=user, entity=right, status=UserSubject.Status.WISH)
    candidate = _candidate(left, right)

    with pytest.raises(EntityResolutionError, match="conflicting user library entries"):
        entity_resolution_service.decide_candidate(
            candidate=candidate,
            outcome=MatchDecision.Outcome.BIND,
            decided_by="manual",
            reason="Unsafe attempted bind.",
        )

    candidate.refresh_from_db()
    assert candidate.status == MatchCandidate.Status.PENDING
    assert not MatchDecision.objects.exists()
    assert not EntityRedirect.objects.exists()


def test_restricted_cluster_is_never_exposed_through_public_member() -> None:
    public = _work("Public")
    restricted = _work(
        "Restricted",
        visibility=Entity.Visibility.RESTRICTED,
    )
    entity_resolution_service.merge(
        source=public,
        target=restricted,
        method=MergeEvent.Method.MANUAL,
        reason="Same entity with restricted source data.",
    )

    client = APIClient()
    assert client.get(f"/api/v1/index/entities/{public.pk}/").status_code == 404
    assert client.get(f"/api/v1/index/entities/{restricted.pk}/").status_code == 404
