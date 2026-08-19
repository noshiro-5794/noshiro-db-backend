import hashlib
import json
import re
from collections.abc import Iterator
from urllib.parse import urlparse

from django.db import transaction

from apps.index.models import (
    Entity,
    Fact,
    FactEvidence,
    MatchCandidate,
    MatchDecision,
    MatchEvidence,
    Observation,
    Predicate,
    ProviderRepresentation,
    Work,
)

from .resolution import EntityResolutionError, entity_resolution_service


class CrossProviderIdentityService:
    POLICY_VERSION = "official-cross-id-v1"
    VNDB_PREDICATE = "external-id-vndb"
    VNDB_ID_PATTERN = re.compile(r"^v[1-9][0-9]*$", re.IGNORECASE)
    VNDB_HOSTS = frozenset({"vndb.org", "www.vndb.org"})

    @transaction.atomic
    def observe_bangumi_work(
        self,
        *,
        entity: Entity,
        observation: Observation,
        payload: dict,
    ) -> None:
        for vndb_id, json_pointer in self.extract_vndb_ids(payload):
            self._record_vndb_fact(
                entity=entity,
                observation=observation,
                vndb_id=vndb_id,
                json_pointer=json_pointer,
            )
            self._reconcile(
                bangumi_entity=entity,
                bangumi_observation=observation,
                vndb_id=vndb_id,
            )

    @transaction.atomic
    def reconcile_vndb_work(
        self,
        *,
        entity: Entity,
        vndb_id: str,
    ) -> None:
        predicate = Predicate.objects.filter(slug=self.VNDB_PREDICATE).first()
        if predicate is None:
            return
        facts = (
            Fact.objects.filter(
                predicate=predicate,
                value=vndb_id.lower(),
                evidence__observation__provider_record__namespace__provider__slug=(
                    "bangumi"
                ),
                evidence__observation__provider_record__status="active",
            )
            .select_related("entity")
            .prefetch_related("evidence__observation")
            .distinct()
        )
        for fact in facts:
            evidence = next(
                (
                    item
                    for item in fact.evidence.all()
                    if item.observation.provider_record_id is not None
                ),
                None,
            )
            if evidence is None:
                continue
            self._bind_verified_pair(
                bangumi_entity=fact.entity,
                vndb_entity=entity,
                bangumi_observation=evidence.observation,
                vndb_id=vndb_id.lower(),
            )

    @classmethod
    def extract_vndb_ids(cls, payload: dict) -> set[tuple[str, str]]:
        return set(cls._walk_values(payload))

    @classmethod
    def _walk_values(
        cls,
        value,
        *,
        pointer: str = "",
        vndb_context: bool = False,
    ) -> Iterator[tuple[str, str]]:
        if isinstance(value, dict):
            local_context = vndb_context or any(
                "vndb" in str(value.get(key, "")).lower()
                for key in ("key", "label", "name")
            )
            for key, child in value.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                yield from cls._walk_values(
                    child,
                    pointer=f"{pointer}/{escaped}",
                    vndb_context=local_context or "vndb" in str(key).lower(),
                )
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                yield from cls._walk_values(
                    child,
                    pointer=f"{pointer}/{index}",
                    vndb_context=vndb_context,
                )
            return
        if not isinstance(value, str):
            return
        text = value.strip()
        if vndb_context and cls.VNDB_ID_PATTERN.fullmatch(text):
            yield text.lower(), pointer or "/"
            return
        parsed = urlparse(text)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in cls.VNDB_HOSTS
        ):
            return
        candidate = parsed.path.strip("/").split("/", 1)[0]
        if cls.VNDB_ID_PATTERN.fullmatch(candidate):
            yield candidate.lower(), pointer or "/"

    def _record_vndb_fact(
        self,
        *,
        entity: Entity,
        observation: Observation,
        vndb_id: str,
        json_pointer: str,
    ) -> None:
        predicate, _ = Predicate.objects.get_or_create(
            slug=self.VNDB_PREDICATE,
            defaults={
                "name": "VNDB identifier",
                "value_type": Predicate.ValueType.STRING,
            },
        )
        value_hash = hashlib.sha256(
            json.dumps(vndb_id, separators=(",", ":")).encode()
        ).hexdigest()
        fact, _ = Fact.objects.get_or_create(
            entity=entity,
            predicate=predicate,
            value_hash=value_hash,
            language="",
            defaults={"value": vndb_id},
        )
        FactEvidence.objects.get_or_create(
            fact=fact,
            observation=observation,
            json_pointer=json_pointer,
        )
        from .fact_resolution import fact_resolution_service

        fact_resolution_service.rebuild(entity=entity, predicate=predicate)

    def _reconcile(
        self,
        *,
        bangumi_entity: Entity,
        bangumi_observation: Observation,
        vndb_id: str,
    ) -> None:
        representation = (
            ProviderRepresentation.objects.filter(
                provider_record__namespace__provider__slug="vndb",
                provider_record__namespace__slug="vn",
                provider_record__external_id=vndb_id,
                provider_record__status="active",
                is_active=True,
            )
            .select_related("entity")
            .first()
        )
        if representation is None:
            return
        self._bind_verified_pair(
            bangumi_entity=bangumi_entity,
            vndb_entity=representation.entity,
            bangumi_observation=bangumi_observation,
            vndb_id=vndb_id,
        )

    def _bind_verified_pair(
        self,
        *,
        bangumi_entity: Entity,
        vndb_entity: Entity,
        bangumi_observation: Observation,
        vndb_id: str,
    ) -> None:
        bangumi_root = entity_resolution_service.resolve(bangumi_entity)
        vndb_root = entity_resolution_service.resolve(vndb_entity)
        if bangumi_root.pk == vndb_root.pk:
            return
        if not self._compatible_galgame_entities(bangumi_root, vndb_root):
            hard_conflicts = ["entity_type"]
        else:
            hard_conflicts = []
            Work.objects.filter(entity=bangumi_root).update(
                work_type=Work.WorkType.GALGAME
            )
        left, right = sorted((bangumi_root, vndb_root), key=lambda item: str(item.pk))
        candidate, _ = MatchCandidate.objects.get_or_create(
            left_entity=left,
            right_entity=right,
            policy_version=self.POLICY_VERSION,
            defaults={
                "score": "1.0000",
                "runner_up_margin": "1.0000",
                "hard_conflicts": hard_conflicts,
            },
        )
        MatchEvidence.objects.get_or_create(
            candidate=candidate,
            evidence_type="official_external_id",
            observation=bangumi_observation,
            defaults={
                "value": {"provider": "vndb", "external_id": vndb_id},
                "weight": "1.0000",
            },
        )
        if candidate.status != MatchCandidate.Status.PENDING:
            return
        if hard_conflicts:
            entity_resolution_service.decide_candidate(
                candidate=candidate,
                outcome=MatchDecision.Outcome.ABSTAIN,
                decided_by="official_external_id",
                reason="Official identifier conflicts with canonical entity types.",
            )
            return
        try:
            entity_resolution_service.decide_candidate(
                candidate=candidate,
                outcome=MatchDecision.Outcome.BIND,
                decided_by="official_external_id",
                reason=f"Bangumi explicitly references VNDB {vndb_id}.",
            )
        except EntityResolutionError as exc:
            entity_resolution_service.decide_candidate(
                candidate=candidate,
                outcome=MatchDecision.Outcome.ABSTAIN,
                decided_by="official_external_id",
                reason=f"Verified identifier could not be bound safely: {exc}",
            )

    @staticmethod
    def _compatible_galgame_entities(left: Entity, right: Entity) -> bool:
        if left.kind != Entity.Kind.WORK or right.kind != Entity.Kind.WORK:
            return False
        allowed = {Work.WorkType.GALGAME, Work.WorkType.GAME}
        left_type = (
            Work.objects.filter(entity=left).values_list("work_type", flat=True).first()
        )
        right_type = (
            Work.objects.filter(entity=right)
            .values_list("work_type", flat=True)
            .first()
        )
        return left_type in allowed and right_type == Work.WorkType.GALGAME


cross_provider_identity_service = CrossProviderIdentityService()
