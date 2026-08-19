import uuid
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.community.models import Activity, CommunityPost
from apps.index.models import (
    Appearance,
    Character,
    Credit,
    DataMigrationRun,
    Entity,
    EntityRelation,
    EntityRelationEvidence,
    Episode,
    Observation,
    Person,
    ProviderRepresentation,
    Staff,
    Subject,
    SubjectCharacterActorRelation,
    SubjectCharacterRelation,
    SubjectStaffRelation,
    SubjectSubjectRelation,
    VoicePerformance,
)
from apps.index.services.knowledge_backfill import KnowledgeGraphBackfillService
from apps.users.models import User, UserSubject

pytestmark = pytest.mark.django_db(transaction=True)


def _subject(
    source_id: int, *, subject_type: str = Subject.SubjectType.ANIME
) -> Subject:
    return Subject.objects.create(
        id=uuid.UUID(int=source_id),
        info_source="bangumi_subject",
        id_source=str(source_id),
        subject_type=subject_type,
        title=f"Subject {source_id}",
    )


def _legacy_graph() -> dict:
    subject = _subject(1)
    related = _subject(2)
    character = Character.objects.create(
        info_source="bangumi_character",
        id_source="10",
        name="Character",
    )
    staff = Staff.objects.create(
        info_source="bangumi_persons",
        id_source="20",
        name="Staff",
        type="Individual",
    )
    actor = Staff.objects.create(
        info_source="bangumi_persons",
        id_source="21",
        name="Actor",
        type="Individual",
    )
    episode = Episode.objects.create(
        info_source="bangumi_episode",
        id_source="100",
        subject=subject,
        title="Episode 1",
    )
    SubjectSubjectRelation.objects.create(
        source=subject,
        target=related,
        relation="Side Story",
    )
    SubjectStaffRelation.objects.create(
        subject=subject,
        staff=staff,
        role="Director",
    )
    SubjectCharacterRelation.objects.create(
        subject=subject,
        character=character,
        role="main",
    )
    SubjectCharacterActorRelation.objects.create(
        subject=subject,
        character=character,
        actor=actor,
    )
    user = User.objects.create_user(email="backfill@example.com")
    library_entry = UserSubject.objects.create(
        user=user,
        subject=subject,
        status=UserSubject.Status.DOING,
    )
    post = CommunityPost.objects.create(
        author=user,
        subject=subject,
        post_type=CommunityPost.PostType.LEGACY_SUBJECT,
        content="Legacy post",
    )
    activity = Activity.objects.create(
        user=user,
        subject=subject,
        activity_type=Activity.ActivityType.POST_CREATED,
        post=post,
    )
    return {
        "subject": subject,
        "related": related,
        "character": character,
        "staff": staff,
        "actor": actor,
        "episode": episode,
        "library_entry": library_entry,
        "post": post,
        "activity": activity,
    }


def _run_id(output: StringIO):
    line = next(
        line for line in output.getvalue().splitlines() if line.startswith("run_id=")
    )
    return line.removeprefix("run_id=")


def test_backfill_pauses_and_resumes_from_persistent_checkpoints() -> None:
    legacy = _legacy_graph()
    output = StringIO()

    call_command(
        "backfill_knowledge_graph",
        batch_size=1,
        max_batches=1,
        stdout=output,
    )

    run = DataMigrationRun.objects.get(pk=_run_id(output))
    subject_checkpoint = run.checkpoints.get(stage="subjects")
    assert run.status == DataMigrationRun.Status.PAUSED
    assert subject_checkpoint.processed_count == 1
    assert not subject_checkpoint.is_complete
    assert Entity.objects.filter(pk=legacy["subject"].pk).exists()
    assert not Entity.objects.filter(pk=legacy["related"].pk).exists()

    call_command(
        "backfill_knowledge_graph",
        resume=run.id,
        batch_size=2,
        stdout=StringIO(),
    )

    run.refresh_from_db()
    assert run.status == DataMigrationRun.Status.SUCCEEDED
    assert not run.checkpoints.filter(is_complete=False).exists()
    assert run.checkpoints.get(stage="subjects").processed_count == 2
    assert ProviderRepresentation.objects.filter(
        entity_id=legacy["subject"].pk,
        method=ProviderRepresentation.Method.LEGACY,
    ).exists()

    legacy["episode"].refresh_from_db()
    legacy["character"].refresh_from_db()
    legacy["staff"].refresh_from_db()
    legacy["actor"].refresh_from_db()
    legacy["library_entry"].refresh_from_db()
    legacy["post"].refresh_from_db()
    legacy["activity"].refresh_from_db()

    assert legacy["episode"].entity_id is not None
    assert legacy["character"].entity_id is not None
    assert legacy["staff"].contributor_id is not None
    assert legacy["actor"].contributor_id is not None
    assert Person.objects.filter(contributor=legacy["staff"].contributor).exists()
    assert Person.objects.filter(contributor=legacy["actor"].contributor).exists()
    assert legacy["library_entry"].entity_id == legacy["subject"].pk
    assert legacy["post"].entity_id == legacy["subject"].pk
    assert legacy["post"].post_type == CommunityPost.PostType.ENTITY
    assert legacy["activity"].entity_id == legacy["subject"].pk

    assert Credit.objects.count() == 1
    assert Appearance.objects.count() == 1
    assert VoicePerformance.objects.count() == 1
    assert EntityRelation.objects.filter(relation_type="side-story").exists()
    assert EntityRelation.objects.filter(relation_type="has-episode").exists()
    assert EntityRelationEvidence.objects.count() == 2


def test_failed_batch_rolls_back_data_and_checkpoint_then_resumes() -> None:
    first = _subject(1)
    second = _subject(2)
    output = StringIO()
    original = KnowledgeGraphBackfillService._process_subject

    def fail_on_second(command, primary_key):
        if primary_key == second.pk:
            raise RuntimeError("injected failure")
        return original(command, primary_key)

    with (
        patch.object(KnowledgeGraphBackfillService, "_process_subject", fail_on_second),
        pytest.raises(CommandError, match="injected failure"),
    ):
        call_command(
            "backfill_knowledge_graph",
            batch_size=1,
            stdout=output,
        )

    run = DataMigrationRun.objects.get(pk=_run_id(output))
    checkpoint = run.checkpoints.get(stage="subjects")
    assert run.status == DataMigrationRun.Status.FAILED
    assert checkpoint.processed_count == 1
    assert checkpoint.cursor == str(first.pk)
    assert Entity.objects.filter(pk=first.pk).exists()
    assert not Entity.objects.filter(pk=second.pk).exists()

    call_command("backfill_knowledge_graph", resume=run.id, stdout=StringIO())

    run.refresh_from_db()
    assert run.status == DataMigrationRun.Status.SUCCEEDED
    assert run.checkpoints.get(stage="subjects").processed_count == 2
    assert Entity.objects.filter(pk=second.pk).exists()


def test_second_complete_run_is_idempotent() -> None:
    _legacy_graph()
    call_command("backfill_knowledge_graph", batch_size=2, stdout=StringIO())

    counts = {
        "entities": Entity.objects.count(),
        "observations": Observation.objects.count(),
        "relations": EntityRelation.objects.count(),
        "relation_evidence": EntityRelationEvidence.objects.count(),
        "credits": Credit.objects.count(),
        "appearances": Appearance.objects.count(),
        "voice_performances": VoicePerformance.objects.count(),
    }
    call_command("backfill_knowledge_graph", batch_size=3, stdout=StringIO())

    assert Entity.objects.count() == counts["entities"]
    assert Observation.objects.count() == counts["observations"]
    assert EntityRelation.objects.count() == counts["relations"]
    assert EntityRelationEvidence.objects.count() == counts["relation_evidence"]
    assert Credit.objects.count() == counts["credits"]
    assert Appearance.objects.count() == counts["appearances"]
    assert VoicePerformance.objects.count() == counts["voice_performances"]


def test_dry_run_does_not_create_operational_or_domain_rows() -> None:
    _subject(1)
    output = StringIO()

    call_command("backfill_knowledge_graph", dry_run=True, stdout=output)

    assert '"subjects"' in output.getvalue()
    assert DataMigrationRun.objects.count() == 0
    assert Entity.objects.count() == 0
