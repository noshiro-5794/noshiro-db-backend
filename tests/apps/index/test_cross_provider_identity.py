import pytest

from apps.index.models import (
    Entity,
    EntityRedirect,
    Fact,
    MatchCandidate,
    MatchDecision,
    MatchEvidence,
    Observation,
    Provider,
    ProviderNamespace,
    ProviderRecord,
    ProviderRepresentation,
    Work,
)
from apps.index.services.identity import CrossProviderIdentityService
from apps.users.models import User, UserSubject

pytestmark = pytest.mark.django_db(transaction=True)


def _provider_record(provider_slug: str, namespace_slug: str, external_id: str):
    provider, _ = Provider.objects.get_or_create(
        slug=provider_slug,
        defaults={"name": provider_slug.title()},
    )
    namespace, _ = ProviderNamespace.objects.get_or_create(
        provider=provider,
        slug=namespace_slug,
        defaults={"resource_type": ProviderNamespace.ResourceType.SUBJECT},
    )
    return ProviderRecord.objects.create(
        namespace=namespace,
        external_id=external_id,
        origin=ProviderRecord.Origin.API,
    )


def _work(work_type: str) -> Entity:
    entity = Entity.objects.create(kind=Entity.Kind.WORK)
    Work.objects.create(entity=entity, work_type=work_type)
    return entity


def _bangumi_observation(payload: dict) -> Observation:
    return Observation.objects.create(
        provider_record=_provider_record("bangumi", "subject", "1"),
        origin=Observation.Origin.LEGACY,
        schema_name="index.work",
        schema_version="1",
        normalized_data=payload,
        normalized_hash="a" * 64,
    )


def _vndb_representation(entity: Entity, *, vndb_id: str = "v1") -> None:
    ProviderRepresentation.objects.create(
        provider_record=_provider_record("vndb", "vn", vndb_id),
        entity=entity,
        mapping_kind=ProviderRepresentation.MappingKind.EXACT,
        method=ProviderRepresentation.Method.PROVIDER,
        confidence=1,
    )


def test_extracts_only_explicit_vndb_identifiers() -> None:
    payload = {
        "name": "A title mentioning v999",
        "infobox": [
            {"key": "VNDB", "value": "v123"},
            {"key": "Official site", "value": "https://vndb.org/v456"},
            {"key": "Unrelated", "value": "v789"},
        ],
    }

    assert CrossProviderIdentityService.extract_vndb_ids(payload) == {
        ("v123", "/infobox/0/value"),
        ("v456", "/infobox/1/value"),
    }


def test_extract_ignores_non_url_text_that_looks_like_protocol_relative_ipv6() -> None:
    payload = {
        "description": (
            "// Connecting to [ PROJECT_0/1 ] ...\r\n"
            "// Connecting to [ PROJECT_0/1 ] ..."
        )
    }

    assert CrossProviderIdentityService.extract_vndb_ids(payload) == set()


def test_official_vndb_identifier_creates_audited_reversible_binding() -> None:
    service = CrossProviderIdentityService()
    bangumi = _work(Work.WorkType.GAME)
    vndb = _work(Work.WorkType.GALGAME)
    _vndb_representation(vndb)
    observation = _bangumi_observation({"infobox": [{"key": "VNDB", "value": "v1"}]})

    service.observe_bangumi_work(
        entity=bangumi,
        observation=observation,
        payload=observation.normalized_data,
    )

    candidate = MatchCandidate.objects.get()
    decision = MatchDecision.objects.get(candidate=candidate)
    assert candidate.status == MatchCandidate.Status.ACCEPTED
    assert decision.outcome == MatchDecision.Outcome.BIND
    assert decision.decided_by == "official_external_id"
    assert MatchEvidence.objects.get(candidate=candidate).value == {
        "provider": "vndb",
        "external_id": "v1",
    }
    assert Fact.objects.get().value == "v1"
    assert EntityRedirect.objects.filter(is_active=True).count() == 1


def test_verified_id_abstains_when_user_library_entries_conflict() -> None:
    service = CrossProviderIdentityService()
    bangumi = _work(Work.WorkType.GAME)
    vndb = _work(Work.WorkType.GALGAME)
    _vndb_representation(vndb)
    user = User.objects.create_user(email="cross-source-conflict@example.com")
    UserSubject.objects.create(
        user=user,
        entity=bangumi,
        status=UserSubject.Status.DOING,
    )
    UserSubject.objects.create(
        user=user,
        entity=vndb,
        status=UserSubject.Status.WISH,
    )
    observation = _bangumi_observation({"infobox": [{"key": "VNDB", "value": "v1"}]})

    service.observe_bangumi_work(
        entity=bangumi,
        observation=observation,
        payload=observation.normalized_data,
    )

    candidate = MatchCandidate.objects.get()
    assert candidate.status == MatchCandidate.Status.ABSTAINED
    assert MatchDecision.objects.get(candidate=candidate).outcome == "abstain"
    assert not EntityRedirect.objects.exists()
