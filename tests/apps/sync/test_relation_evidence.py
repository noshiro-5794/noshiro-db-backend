from unittest.mock import patch

import pytest

from apps.index.models import (
    CatalogSource,
    Character,
    RelationEvidence,
    Staff,
    Subject,
    SubjectCharacterActorRelation,
    SubjectCharacterRelation,
    SubjectStaffRelation,
    SubjectSubjectRelation,
)
from apps.sync.providers.bangumi import BANGUMI_SUBJECT_NAMESPACE
from apps.sync.services.relation_service import relation_service
from apps.sync.services.source_record_service import source_record_service

pytestmark = pytest.mark.django_db


def _subject(source_id: int) -> Subject:
    return Subject.objects.create(
        info_source="bangumi_subject",
        id_source=str(source_id),
        title=f"Subject {source_id}",
    )


def _sources() -> tuple[CatalogSource, CatalogSource]:
    bangumi = source_record_service.get_or_create_namespace(
        BANGUMI_SUBJECT_NAMESPACE
    ).source
    other = CatalogSource.objects.create(slug="anilist", name="AniList")
    return bangumi, other


def test_bangumi_sync_removes_only_its_relation_evidence() -> None:
    subject = _subject(1)
    shared_target = _subject(2)
    bangumi_only_target = _subject(3)
    bangumi, other = _sources()

    shared = SubjectSubjectRelation.objects.create(
        source=subject,
        target=shared_target,
        relation="sequel",
    )
    bangumi_only = SubjectSubjectRelation.objects.create(
        source=subject,
        target=bangumi_only_target,
        relation="prequel",
    )
    RelationEvidence.objects.create(source=bangumi, subject_relation=shared)
    RelationEvidence.objects.create(source=other, subject_relation=shared)
    RelationEvidence.objects.create(source=bangumi, subject_relation=bangumi_only)

    with (
        patch.object(
            relation_service,
            "_map_subjects",
            return_value={},
        ),
        patch(
            "apps.sync.services.relation_service.bangumi_client.fetch_subject_subjects",
            return_value=[],
        ),
    ):
        relation_service.upsert_subject_relation(1)

    assert SubjectSubjectRelation.objects.filter(pk=shared.pk).exists()
    assert not SubjectSubjectRelation.objects.filter(pk=bangumi_only.pk).exists()
    assert RelationEvidence.objects.filter(
        source=other,
        subject_relation=shared,
    ).exists()
    assert not RelationEvidence.objects.filter(
        source=bangumi,
        subject_relation=shared,
    ).exists()


def test_bangumi_sync_keeps_shared_staff_character_and_actor_relations() -> None:
    subject = _subject(10)
    staff = Staff.objects.create(info_source="bangumi_persons", id_source="11")
    character = Character.objects.create(
        info_source="bangumi_character",
        id_source="12",
    )
    actor = Staff.objects.create(info_source="bangumi_persons", id_source="13")
    bangumi, other = _sources()

    staff_relation = SubjectStaffRelation.objects.create(
        subject=subject,
        staff=staff,
        role="director",
    )
    character_relation = SubjectCharacterRelation.objects.create(
        subject=subject,
        character=character,
        role="main",
    )
    actor_relation = SubjectCharacterActorRelation.objects.create(
        subject=subject,
        character=character,
        actor=actor,
    )
    for field, relation in (
        ("staff_relation", staff_relation),
        ("character_relation", character_relation),
        ("character_actor_relation", actor_relation),
    ):
        RelationEvidence.objects.create(source=bangumi, **{field: relation})
        RelationEvidence.objects.create(source=other, **{field: relation})

    with (
        patch(
            "apps.sync.services.relation_service.bangumi_client.fetch_subject_persons",
            return_value=[],
        ),
        patch(
            "apps.sync.services.relation_service.bangumi_client.fetch_subject_characters",
            return_value=[],
        ),
    ):
        relation_service.upsert_staff_relation(10)
        relation_service.upsert_character_relation(10)

    assert SubjectStaffRelation.objects.filter(pk=staff_relation.pk).exists()
    assert SubjectCharacterRelation.objects.filter(pk=character_relation.pk).exists()
    assert SubjectCharacterActorRelation.objects.filter(pk=actor_relation.pk).exists()
    assert RelationEvidence.objects.filter(source=other).count() == 3
    assert RelationEvidence.objects.filter(source=bangumi).count() == 0
