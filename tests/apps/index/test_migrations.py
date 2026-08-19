import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def test_index_0015_deduplicates_airing_events_and_preserves_decisions() -> None:
    migrate_from = [("index", "0014_entitydescription_safety_fact_safety")]
    migrate_to = [
        (
            "index",
            "0015_remove_resolutiondecision_uq_active_resolution_decision_and_more",
        )
    ]
    executor = MigrationExecutor(connection)

    try:
        executor.migrate(migrate_from)
        old_apps = executor.loader.project_state(migrate_from).apps
        Entity = old_apps.get_model("index", "Entity")
        Work = old_apps.get_model("index", "Work")
        Provider = old_apps.get_model("index", "Provider")
        ProviderNamespace = old_apps.get_model("index", "ProviderNamespace")
        ProviderRecord = old_apps.get_model("index", "ProviderRecord")
        Observation = old_apps.get_model("index", "Observation")
        AiringEvent = old_apps.get_model("index", "AiringEvent")
        Predicate = old_apps.get_model("index", "Predicate")
        Fact = old_apps.get_model("index", "Fact")
        ResolutionDecision = old_apps.get_model("index", "ResolutionDecision")

        entity = Entity.objects.create(kind="work")
        work = Work.objects.create(entity=entity, work_type="anime")
        provider = Provider.objects.create(slug="migration-test", name="Migration Test")
        namespace = ProviderNamespace.objects.create(
            provider=provider,
            slug="schedule",
            resource_type="schedule",
        )
        record = ProviderRecord.objects.create(
            namespace=namespace,
            external_id="weekly",
            origin="api",
        )
        first_observation = Observation.objects.create(
            provider_record=record,
            origin="legacy",
            schema_name="index.schedule",
            schema_version="1",
            normalized_data={"version": 1},
            normalized_hash="1" * 64,
        )
        second_observation = Observation.objects.create(
            provider_record=record,
            origin="legacy",
            schema_name="index.schedule",
            schema_version="1",
            normalized_data={"version": 2},
            normalized_hash="2" * 64,
        )
        event = {
            "work": work,
            "weekday": 3,
            "precision": "weekday",
            "raw_value": "Wednesday",
        }
        AiringEvent.objects.create(**event, observation=first_observation)
        AiringEvent.objects.create(**event, observation=first_observation)
        AiringEvent.objects.create(**event, observation=second_observation)

        predicate = Predicate.objects.create(
            slug="migration-test",
            name="Migration test",
            value_type="string",
        )
        fact = Fact.objects.create(
            id=uuid.uuid4(),
            entity=entity,
            predicate=predicate,
            value="preserved",
            value_hash="f" * 64,
        )
        decision = ResolutionDecision.objects.create(
            entity=entity,
            predicate=predicate,
            selected_fact=fact,
            policy_version="before-0015",
            reason="Must survive migration",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(migrate_to)
        new_apps = executor.loader.project_state(migrate_to).apps
        NewAiringEvent = new_apps.get_model("index", "AiringEvent")
        NewResolutionDecision = new_apps.get_model("index", "ResolutionDecision")

        events = NewAiringEvent.objects.filter(work_id=work.pk)
        assert events.count() == 2
        assert events.values("observation_id").distinct().count() == 2
        migrated_decision = NewResolutionDecision.objects.get(pk=decision.pk)
        assert migrated_decision.selected_fact_id == fact.pk
        assert migrated_decision.language == ""
        assert migrated_decision.policy_version == "before-0015"
    finally:
        MigrationExecutor(connection).migrate(migrate_to)
