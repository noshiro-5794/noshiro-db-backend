from django.db.models import F, Q, QuerySet

from apps.index.models import (
    AiringEvent,
    Appearance,
    ContentRating,
    Credit,
    EntityDescription,
    EntityMedia,
    EntityName,
    EntityRelation,
    EntityRelationEvidence,
    EntityTerm,
    ExternalLink,
    Fact,
    ProviderRecord,
    ReleaseWork,
    ReleaseWorkEvidence,
    VoicePerformance,
)


def selected_observation_support(prefix: str = "observation") -> Q:
    """Match rows supported by the observation selected for its mapper output."""
    field = f"{prefix}__" if prefix else ""
    provider_record = f"{field}provider_record"
    return ~Q(
        **{
            f"{provider_record}__namespace__provider__redistribution_policy": (
                "forbidden"
            )
        }
    ) & Q(
        **{
            f"{field}isnull": False,
            f"{provider_record}__status": ProviderRecord.Status.ACTIVE,
            f"{field}current_projections__isnull": False,
            f"{field}current_projections__provider_record_id": F(
                f"{provider_record}__id"
            ),
        }
    )


def current_observation_support(prefix: str = "observation") -> Q:
    """Match source-independent rows or evidence selected by the mapper cursor."""
    field = f"{prefix}__" if prefix else ""
    return Q(**{f"{field}isnull": True}) | selected_observation_support(prefix)


def current_entity_names() -> QuerySet[EntityName]:
    return EntityName.objects.filter(
        Q(observation__isnull=True, provider_record__isnull=True)
        | selected_observation_support()
    ).distinct()


def current_entity_descriptions() -> QuerySet[EntityDescription]:
    return EntityDescription.objects.filter(
        Q(observation__isnull=True, provider_record__isnull=True)
        | selected_observation_support()
    ).distinct()


def current_entity_media() -> QuerySet[EntityMedia]:
    return EntityMedia.objects.filter(
        Q(observation__isnull=True, asset__provider_record__isnull=True)
        | selected_observation_support()
    ).distinct()


def current_external_links() -> QuerySet[ExternalLink]:
    return ExternalLink.objects.filter(
        Q(observation__isnull=True, provider_record__isnull=True)
        | selected_observation_support()
    ).distinct()


def current_content_ratings() -> QuerySet[ContentRating]:
    return ContentRating.objects.filter(selected_observation_support()).distinct()


def current_facts() -> QuerySet[Fact]:
    return (
        Fact.objects.filter(
            Q(evidence__isnull=True)
            | current_observation_support("evidence__observation")
        )
        .exclude(status=Fact.Status.REJECTED)
        .distinct()
    )


def current_airing_events() -> QuerySet[AiringEvent]:
    return AiringEvent.objects.filter(current_observation_support()).distinct()


def current_entity_relations() -> QuerySet[EntityRelation]:
    return EntityRelation.objects.filter(
        Q(evidence__isnull=True) | current_observation_support("evidence__observation")
    ).distinct()


def current_entity_relation_evidence() -> QuerySet[EntityRelationEvidence]:
    return EntityRelationEvidence.objects.filter(
        selected_observation_support()
    ).distinct()


def current_credits() -> QuerySet[Credit]:
    return Credit.objects.filter(current_observation_support()).distinct()


def current_appearances() -> QuerySet[Appearance]:
    return Appearance.objects.filter(current_observation_support()).distinct()


def current_voice_performances() -> QuerySet[VoicePerformance]:
    return VoicePerformance.objects.filter(
        current_observation_support()
        & current_observation_support("appearance__observation")
    ).distinct()


def current_entity_terms() -> QuerySet[EntityTerm]:
    return EntityTerm.objects.filter(current_observation_support()).distinct()


def current_release_work_links() -> QuerySet[ReleaseWork]:
    return ReleaseWork.objects.filter(
        Q(evidence__isnull=True) | current_observation_support("evidence__observation")
    ).distinct()


def current_release_work_evidence() -> QuerySet[ReleaseWorkEvidence]:
    return ReleaseWorkEvidence.objects.filter(selected_observation_support()).distinct()
