import uuid

from django.core.exceptions import ObjectDoesNotExist

from apps.index.models import Entity, MatchCandidate
from apps.index.selectors.current import current_entity_relations
from apps.index.selectors.projections import (
    entity_detail,
    entity_queryset,
    entity_summary,
)
from apps.index.services import entity_resolution_service


def search_public_entities(
    *,
    query: str = "",
    collection: str = "",
    language: str = "",
    limit: int = 20,
) -> dict:
    bounded_limit = max(1, min(limit, 50))
    entities = entity_queryset(
        keyword=query.strip()[:256],
        collection=collection.strip()[:64],
        scope="all",
    )[:bounded_limit]
    return {
        "results": [
            entity_summary(entity, language=language[:35], safe=True)
            for entity in entities
        ]
    }


def get_public_entity(*, entity_id: uuid.UUID, language: str = "") -> dict:
    try:
        entity = Entity.objects.prefetch_related(
            "names",
            "descriptions",
            "media__asset",
            "index_memberships__collection",
            "provider_representations__provider_record__namespace__provider",
        ).get(pk=entity_id)
    except Entity.DoesNotExist as exc:
        raise ValueError("Public entity not found.") from exc
    entity = entity_resolution_service.resolve(entity)
    if (
        entity.lifecycle != Entity.Lifecycle.ACTIVE
        or not entity_resolution_service.is_public(entity)
    ):
        raise ValueError("Public entity not found.")
    return entity_detail(entity, language=language[:35], safe=True)


def get_public_relations(*, entity_id: uuid.UUID, language: str = "") -> dict:
    get_public_entity(entity_id=entity_id, language=language)
    entity = Entity.objects.get(pk=entity_id)
    entity = entity_resolution_service.resolve(entity)
    relations = (
        current_entity_relations()
        .filter(
            from_entity_id__in=entity_resolution_service.cluster_ids(entity),
        )
        .select_related("to_entity")[:100]
    )
    results = []
    seen = set()
    for relation in relations:
        target = entity_resolution_service.resolve(relation.to_entity)
        if (
            target.lifecycle != Entity.Lifecycle.ACTIVE
            or not entity_resolution_service.is_public(target)
        ):
            continue
        key = (relation.relation_type, target.pk)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "relation_type": relation.relation_type,
                "target": entity_summary(target, language=language[:35], safe=True),
            }
        )
    return {"results": results}


def get_match_candidate(candidate_id: uuid.UUID) -> dict:
    try:
        candidate = (
            MatchCandidate.objects.select_related("left_entity", "right_entity")
            .prefetch_related(
                "left_entity__names",
                "right_entity__names",
                "left_entity__media__asset",
                "right_entity__media__asset",
                "left_entity__index_memberships__collection",
                "right_entity__index_memberships__collection",
                "left_entity__provider_representations__provider_record__namespace__provider",
                "right_entity__provider_representations__provider_record__namespace__provider",
                "evidence",
            )
            .get(pk=candidate_id)
        )
    except ObjectDoesNotExist as exc:
        raise ValueError("Match candidate not found.") from exc
    return {
        "id": str(candidate.id),
        "status": candidate.status,
        "score": str(candidate.score),
        "runner_up_margin": str(candidate.runner_up_margin),
        "policy_version": candidate.policy_version,
        "hard_conflicts": candidate.hard_conflicts,
        "left_entity": entity_summary(candidate.left_entity, safe=True),
        "right_entity": entity_summary(candidate.right_entity, safe=True),
        "evidence": [
            {
                "evidence_type": item.evidence_type,
                "value": item.value,
                "weight": str(item.weight),
            }
            for item in candidate.evidence.all()
        ],
    }
