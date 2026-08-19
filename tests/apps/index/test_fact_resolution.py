import pytest

from apps.index.models import Entity, Fact, Predicate, ResolutionDecision, Work
from apps.index.services import fact_resolution_service, knowledge_ingestion_service

from .projection_fixtures import ALTERNATE_NAMESPACE, observation

pytestmark = pytest.mark.django_db


def test_fact_resolution_selects_a_stronger_value_and_abstains_on_a_tie() -> None:
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    Work.objects.create(entity=entity, work_type=Work.WorkType.GALGAME)
    first = observation({"version": "fact-resolution-1"})
    first_fact = knowledge_ingestion_service.record_fact(
        entity=entity,
        observation=first,
        slug="developer",
        name="Developer",
        value="Studio A",
        value_type=Predicate.ValueType.STRING,
        json_pointer="/developer",
    )
    second = observation(
        {"version": "fact-resolution-2"},
        namespace_spec=ALTERNATE_NAMESPACE,
    )
    second_fact = knowledge_ingestion_service.record_fact(
        entity=entity,
        observation=second,
        slug="developer",
        name="Developer",
        value="Studio B",
        value_type=Predicate.ValueType.STRING,
        json_pointer="/developer",
    )

    first_fact.refresh_from_db()
    second_fact.refresh_from_db()
    decision = ResolutionDecision.objects.get(is_active=True)
    assert decision.selected_fact is None
    assert {fact.status for fact in (first_fact, second_fact)} == {
        Fact.Status.CANDIDATE
    }
    assert {fact.value for fact in fact_resolution_service.projected(entity)} == {
        "Studio A",
        "Studio B",
    }

    second_fact.confidence = "0.9900"
    second_fact.save(update_fields=["confidence", "updated_at"])
    decision = fact_resolution_service.rebuild(
        entity=entity,
        predicate=second_fact.predicate,
    )

    first_fact.refresh_from_db()
    second_fact.refresh_from_db()
    assert decision.selected_fact == first_fact
    assert first_fact.status == Fact.Status.SELECTED
    assert second_fact.status == Fact.Status.CANDIDATE
    assert [fact.value for fact in fact_resolution_service.projected(entity)] == [
        "Studio A"
    ]
    assert ResolutionDecision.objects.filter(is_active=False).exists()
