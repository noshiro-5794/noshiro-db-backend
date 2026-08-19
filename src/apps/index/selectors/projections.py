from django.db.models import Prefetch

from apps.index.models import ContentSafety, Entity, EntityName, IndexMembership, Work
from apps.index.selectors.current import (
    current_content_ratings,
    current_entity_descriptions,
    current_entity_media,
    current_entity_names,
    current_external_links,
)
from apps.index.services import entity_resolution_service, fact_resolution_service


def preferred_name(entity: Entity, *, language: str = "") -> str:
    root = entity_resolution_service.resolve(entity)
    names = _projection_rows(
        root,
        cache_name="_current_names",
        queryset=current_entity_names(),
    )
    if not names:
        return "Untitled"
    language = language or ""
    candidates = [
        name
        for name in names
        if name.language and language and name.language.lower() == language.lower()
    ]
    if not candidates and language:
        primary = language.split("-")[0].lower()
        candidates = [
            name for name in names if name.language.lower().split("-")[0] == primary
        ]
    candidates = candidates or [
        name
        for name in names
        if name.is_original or name.kind == EntityName.Kind.ORIGINAL
    ]
    candidates = candidates or names
    return sorted(candidates, key=lambda item: (not item.is_official, item.id))[0].text


def field_provenance(*, provider_record, observation) -> dict | None:
    if provider_record is None:
        return None
    revision_id = None
    if observation is not None and observation.mapping_run_id is not None:
        revision_id = observation.mapping_run.revision_id
    return {
        "provider": provider_record.namespace.provider.slug,
        "namespace": provider_record.namespace.slug,
        "external_id": provider_record.external_id,
        "observation_id": observation.id if observation is not None else None,
        "revision_id": revision_id,
        "observed_at": observation.observed_at if observation is not None else None,
    }


def request_allows_adult_content(request) -> bool:
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    profile = getattr(user, "profile", None)
    return bool(
        profile
        and profile.show_adult_content
        and profile.adult_content_confirmed_at is not None
    )


def entity_summary(
    entity: Entity,
    *,
    language: str = "",
    safe: bool = True,
    adult_allowed: bool = False,
    spoiler_level: int = 0,
) -> dict:
    root = entity_resolution_service.resolve(entity)
    cluster_ids = entity_resolution_service.cluster_ids(root)
    cluster_entities = list(Entity.objects.filter(pk__in=cluster_ids))
    audience = (
        Entity.Audience.ADULT
        if any(item.audience == Entity.Audience.ADULT for item in cluster_entities)
        else root.audience
    )
    work = Work.objects.filter(entity_id__in=cluster_ids).exclude(
        work_type=Work.WorkType.UNCLASSIFIED
    ).order_by("created_at", "entity_id").first() or getattr(root, "work", None)
    memberships = [
        membership.collection.slug
        for membership in IndexMembership.objects.filter(
            entity_id__in=cluster_ids
        ).select_related("collection")
        if membership.listing_state == "listed"
    ]
    media = []
    content_allowed = not safe or adult_allowed or audience != Entity.Audience.ADULT
    entity_spoiler_allowed = not safe or all(
        item.spoiler_level <= spoiler_level for item in cluster_entities
    )
    if content_allowed and entity_spoiler_allowed:
        media_links = _projection_rows(
            root,
            cache_name="_current_media",
            queryset=current_entity_media().select_related(
                "asset__provider_record__namespace__provider",
                "observation__mapping_run",
            ),
        )
        media = [
            {
                "url": link.asset.url,
                "purpose": link.purpose,
                "safety": link.asset.safety,
                "provenance": field_provenance(
                    provider_record=link.asset.provider_record,
                    observation=link.observation,
                ),
            }
            for link in media_links
            if (
                not safe
                or adult_allowed
                or link.asset.safety not in {"explicit", "suggestive"}
            )
            and (not safe or link.asset.spoiler_level <= spoiler_level)
        ]
    return {
        "id": str(root.id),
        "entity_type": root.kind,
        "lifecycle": root.lifecycle,
        "audience": audience,
        "work_type": work.work_type if work else None,
        "display_name": preferred_name(root, language=language),
        "collections": sorted(set(memberships)),
        "media": media,
    }


def entity_detail(
    entity: Entity,
    *,
    language: str = "",
    safe: bool = True,
    adult_allowed: bool = False,
    spoiler_level: int = 0,
) -> dict:
    root = entity_resolution_service.resolve(entity)
    data = entity_summary(
        root,
        language=language,
        safe=safe,
        adult_allowed=adult_allowed,
        spoiler_level=spoiler_level,
    )
    data["names"] = [
        {
            "text": name.text,
            "language": name.language,
            "script": name.script,
            "region": name.region,
            "kind": name.kind,
            "is_official": name.is_official,
            "is_original": name.is_original,
            "is_machine_generated": name.is_machine_generated,
            "is_reviewed": name.is_reviewed,
            "provenance": field_provenance(
                provider_record=name.provider_record,
                observation=name.observation,
            ),
        }
        for name in _projection_rows(
            root,
            cache_name="_current_names",
            queryset=current_entity_names().select_related(
                "provider_record__namespace__provider",
                "observation__mapping_run",
            ),
        )
    ]
    data["descriptions"] = [
        {
            "text": description.text,
            "language": description.language,
            "is_official": description.is_official,
            "is_machine_generated": description.is_machine_generated,
            "is_reviewed": description.is_reviewed,
            "spoiler_level": description.spoiler_level,
            "safety": description.safety,
            "provenance": field_provenance(
                provider_record=description.provider_record,
                observation=description.observation,
            ),
        }
        for description in _projection_rows(
            root,
            cache_name="_current_descriptions",
            queryset=current_entity_descriptions().select_related(
                "provider_record__namespace__provider",
                "observation__mapping_run",
            ),
        )
        if (not safe or adult_allowed or data["audience"] != Entity.Audience.ADULT)
        and (
            not safe
            or adult_allowed
            or description.safety
            not in {ContentSafety.EXPLICIT, ContentSafety.SUGGESTIVE}
        )
        and (not safe or description.spoiler_level <= spoiler_level)
    ]
    data["facts"] = [
        {
            "predicate": fact.predicate.slug,
            "value": fact.value,
            "language": fact.language,
            "status": fact.status,
            "confidence": str(fact.confidence),
            "spoiler_level": fact.spoiler_level,
            "safety": fact.safety,
            "is_machine_generated": fact.is_machine_generated,
            "evidence": [
                {
                    **field_provenance(
                        provider_record=evidence.observation.provider_record,
                        observation=evidence.observation,
                    ),
                    "json_pointer": evidence.json_pointer,
                }
                for evidence in fact.evidence.all()
            ],
        }
        for fact in fact_resolution_service.projected(root)
        if (not safe or adult_allowed or data["audience"] != Entity.Audience.ADULT)
        and (
            not safe
            or adult_allowed
            or fact.safety not in {ContentSafety.EXPLICIT, ContentSafety.SUGGESTIVE}
        )
        and (not safe or fact.spoiler_level <= spoiler_level)
    ]
    data["external_links"] = [
        {
            "url": link.url,
            "label": link.label,
            "link_type": link.link_type,
            "provenance": field_provenance(
                provider_record=link.provider_record,
                observation=link.observation,
            ),
        }
        for link in current_external_links()
        .filter(entity_id__in=entity_resolution_service.cluster_ids(root))
        .select_related(
            "provider_record__namespace__provider",
            "observation__mapping_run",
        )
        .order_by("provider_record_id", "url", "id")
    ]
    data["content_ratings"] = [
        {
            "system": rating.system,
            "value": rating.value,
            "region": rating.region,
            "minimum_age": rating.minimum_age,
            "provenance": field_provenance(
                provider_record=rating.provider_record,
                observation=rating.observation,
            ),
        }
        for rating in current_content_ratings()
        .filter(entity_id__in=entity_resolution_service.cluster_ids(root))
        .select_related(
            "provider_record__namespace__provider",
            "observation__mapping_run",
        )
        .order_by("system", "region", "value", "id")
    ]
    data["sources"] = [
        {
            "provider": representation.provider_record.namespace.provider.slug,
            "namespace": representation.provider_record.namespace.slug,
            "external_id": representation.provider_record.external_id,
            "url": representation.provider_record.canonical_url,
            "mapping_kind": representation.mapping_kind,
            "method": representation.method,
            "confidence": str(representation.confidence),
            "last_seen_at": representation.provider_record.last_seen_at,
        }
        for representation in root.provider_representations.model.objects.filter(
            entity_id__in=entity_resolution_service.cluster_ids(root),
            is_active=True,
        )
        .exclude(
            provider_record__namespace__provider__redistribution_policy="forbidden"
        )
        .select_related("provider_record__namespace__provider")
        .order_by(
            "provider_record__namespace__provider__slug",
            "provider_record__namespace__slug",
            "provider_record__external_id",
        )
    ]
    return data


def entity_queryset(*, keyword: str = "", collection: str = "", scope: str = ""):
    qs = Entity.objects.filter(
        lifecycle=Entity.Lifecycle.ACTIVE,
        visibility=Entity.Visibility.PUBLIC,
    ).prefetch_related(
        Prefetch(
            "names",
            queryset=current_entity_names(),
            to_attr="_current_names",
        ),
        Prefetch(
            "media",
            queryset=current_entity_media().select_related("asset"),
            to_attr="_current_media",
        ),
        "index_memberships__collection",
        "provider_representations__provider_record__namespace__provider",
    )
    collection_slugs = (collection,) if collection else ("anime", "galgame")
    if collection or scope != "all":
        listed_ids = IndexMembership.objects.filter(
            collection__slug__in=collection_slugs,
            listing_state="listed",
        ).values_list("entity_id", flat=True)
        canonical_ids = {
            entity_resolution_service.resolve(entity).pk
            for entity in Entity.objects.filter(pk__in=listed_ids)
        }
        qs = qs.filter(pk__in=canonical_ids)
    if keyword:
        matching_ids = set(
            current_entity_names()
            .filter(text__icontains=keyword)
            .values_list("entity_id", flat=True)
        )
        matching_ids.update(
            current_external_links()
            .filter(url__icontains=keyword)
            .values_list("entity_id", flat=True)
        )
        canonical_ids = {
            entity_resolution_service.resolve(entity).pk
            for entity in Entity.objects.filter(pk__in=matching_ids)
        }
        qs = qs.filter(pk__in=canonical_ids)
    return qs.distinct().order_by("-updated_at", "id")


def _projection_rows(entity: Entity, *, cache_name: str, queryset) -> list:
    cluster_ids = entity_resolution_service.cluster_ids(entity)
    cached = getattr(entity, cache_name, None)
    if cached is not None and cluster_ids == {entity.pk}:
        return list(cached)
    return list(queryset.filter(entity_id__in=cluster_ids))
