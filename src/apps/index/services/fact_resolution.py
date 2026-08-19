from collections import defaultdict

from django.db import transaction

from apps.index.models import Entity, Fact, Predicate, ResolutionDecision
from apps.index.selectors.current import current_facts

from .resolution import entity_resolution_service


class FactResolutionService:
    POLICY_VERSION = "fact-resolution-v1"

    @transaction.atomic
    def rebuild(
        self,
        *,
        entity: Entity,
        predicate: Predicate,
        language: str = "",
    ) -> ResolutionDecision:
        root = entity_resolution_service.resolve(entity)
        facts = list(
            current_facts()
            .filter(
                entity_id__in=entity_resolution_service.cluster_ids(root),
                predicate=predicate,
                language=language,
            )
            .order_by("-confidence", "id")
        )
        selected_fact, reason = self._select(facts)
        ResolutionDecision.objects.select_for_update().filter(
            entity=root,
            predicate=predicate,
            language=language,
            is_active=True,
        ).update(is_active=False)
        decision = ResolutionDecision.objects.create(
            entity=root,
            predicate=predicate,
            language=language,
            selected_fact=selected_fact,
            policy_version=self.POLICY_VERSION,
            reason=reason,
        )
        Fact.objects.filter(
            entity_id__in=entity_resolution_service.cluster_ids(root),
            predicate=predicate,
            language=language,
        ).exclude(status=Fact.Status.REJECTED).update(status=Fact.Status.CANDIDATE)
        if selected_fact is not None:
            Fact.objects.filter(pk=selected_fact.pk).update(status=Fact.Status.SELECTED)
        return decision

    def rebuild_entity(self, *, entity: Entity) -> int:
        root = entity_resolution_service.resolve(entity)
        fields = list(
            current_facts()
            .filter(entity_id__in=entity_resolution_service.cluster_ids(root))
            .values_list("predicate_id", "language")
            .distinct()
        )
        for predicate_id, language in fields:
            self.rebuild(
                entity=root,
                predicate=Predicate.objects.get(pk=predicate_id),
                language=language,
            )
        return len(fields)

    @staticmethod
    def _select(facts: list[Fact]) -> tuple[Fact | None, str]:
        if not facts:
            return None, "No current supported fact is available."
        values: dict[tuple[str, str], list[Fact]] = defaultdict(list)
        for fact in facts:
            values[(fact.value_hash, fact.language)].append(fact)
        ranked = sorted(
            values.values(),
            key=lambda group: (
                -max(item.confidence for item in group),
                -sum(item.evidence.count() for item in group),
                str(min(item.id for item in group)),
            ),
        )
        if len(ranked) > 1:
            first_confidence = max(item.confidence for item in ranked[0])
            second_confidence = max(item.confidence for item in ranked[1])
            if first_confidence == second_confidence:
                return (
                    None,
                    "Conflicting current facts have equal confidence; abstained.",
                )
        selected = sorted(
            ranked[0],
            key=lambda item: (-item.confidence, -item.evidence.count(), str(item.id)),
        )[0]
        return selected, "Selected by confidence and independent evidence count."

    @staticmethod
    def projected(entity: Entity) -> list[Fact]:
        root = entity_resolution_service.resolve(entity)
        cluster_ids = entity_resolution_service.cluster_ids(root)
        facts = list(
            current_facts()
            .filter(entity_id__in=cluster_ids)
            .select_related("predicate")
            .prefetch_related(
                "evidence__observation__provider_record__namespace__provider",
                "evidence__observation__mapping_run",
            )
            .order_by("predicate__slug", "language", "id")
        )
        decisions = {
            (decision.predicate_id, decision.language): decision.selected_fact_id
            for decision in ResolutionDecision.objects.filter(
                entity=root,
                is_active=True,
            )
        }
        return [
            fact
            for fact in facts
            if decisions.get((fact.predicate_id, fact.language), fact.id)
            in {None, fact.id}
        ]


fact_resolution_service = FactResolutionService()
