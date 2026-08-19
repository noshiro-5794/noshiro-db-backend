from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.index.exceptions import EntityResolutionError
from apps.index.models import (
    Entity,
    EntityRedirect,
    MatchCandidate,
    MatchDecision,
    MergeEvent,
    SplitEvent,
)


class EntityResolutionService:
    MAX_REDIRECT_DEPTH = 32

    def resolve(self, entity: Entity) -> Entity:
        visited = set()
        current = entity
        for _ in range(self.MAX_REDIRECT_DEPTH):
            if current.pk in visited:
                raise EntityResolutionError("Entity redirect cycle detected.")
            visited.add(current.pk)
            redirect = (
                EntityRedirect.objects.select_related("target_entity")
                .filter(source_entity=current, is_active=True)
                .first()
            )
            if redirect is None:
                return current
            current = redirect.target_entity
        raise EntityResolutionError("Entity redirect depth exceeded.")

    def cluster_ids(self, entity: Entity) -> set:
        """Return the canonical entity and every entity redirected into it."""
        root = self.resolve(entity)
        entity_ids = {root.pk}
        frontier = {root.pk}
        for _ in range(self.MAX_REDIRECT_DEPTH):
            sources = set(
                EntityRedirect.objects.filter(
                    target_entity_id__in=frontier,
                    is_active=True,
                ).values_list("source_entity_id", flat=True)
            )
            sources -= entity_ids
            if not sources:
                return entity_ids
            entity_ids.update(sources)
            frontier = sources
        raise EntityResolutionError("Entity redirect cluster depth exceeded.")

    def is_public(self, entity: Entity) -> bool:
        cluster = Entity.objects.filter(pk__in=self.cluster_ids(entity))
        return not cluster.exclude(visibility=Entity.Visibility.PUBLIC).exists()

    @transaction.atomic
    def merge(
        self,
        *,
        source: Entity,
        target: Entity,
        method: str,
        reason: str,
        snapshot: dict | None = None,
    ) -> MergeEvent:
        source = self.resolve(Entity.objects.select_for_update().get(pk=source.pk))
        target = self.resolve(Entity.objects.select_for_update().get(pk=target.pk))
        if source.pk == target.pk:
            raise EntityResolutionError("Cannot merge an entity into itself.")
        if source.kind != target.kind:
            raise EntityResolutionError("Cannot merge entities of different kinds.")
        if self._safety_rank(source) > self._safety_rank(target):
            raise EntityResolutionError(
                "Canonical entity must preserve the strictest safety classification."
            )
        self._ensure_no_user_library_conflict(source=source, target=target)
        snapshot = snapshot or self._merge_snapshot(source=source, target=target)
        event = MergeEvent.objects.create(
            source_entity=source,
            target_entity=target,
            method=method,
            reason=reason,
            snapshot=snapshot,
        )
        EntityRedirect.objects.create(
            source_entity=source,
            target_entity=target,
            merge_event=event,
        )
        source.lifecycle = Entity.Lifecycle.MERGED
        source.save(update_fields=["lifecycle", "updated_at"])
        from .fact_resolution import fact_resolution_service

        fact_resolution_service.rebuild_entity(entity=target)
        return event

    @transaction.atomic
    def split(self, *, merge_event: MergeEvent, reason: str) -> SplitEvent:
        event = MergeEvent.objects.select_for_update().get(pk=merge_event.pk)
        if event.reversed_at is not None:
            raise EntityResolutionError("Merge event is already reversed.")
        redirect = EntityRedirect.objects.select_for_update().get(merge_event=event)
        redirect.is_active = False
        redirect.save(update_fields=["is_active", "updated_at"])
        event.reversed_at = timezone.now()
        event.save(update_fields=["reversed_at", "updated_at"])
        event.source_entity.lifecycle = Entity.Lifecycle.ACTIVE
        event.source_entity.save(update_fields=["lifecycle", "updated_at"])
        from .fact_resolution import fact_resolution_service

        fact_resolution_service.rebuild_entity(entity=event.target_entity)
        fact_resolution_service.rebuild_entity(entity=event.source_entity)
        return SplitEvent.objects.create(
            merge_event=event,
            reason=reason,
            restored_snapshot=event.snapshot,
        )

    @transaction.atomic
    def decide_candidate(
        self,
        *,
        candidate: MatchCandidate,
        outcome: str,
        decided_by: str,
        reason: str,
    ) -> MatchDecision:
        candidate = (
            MatchCandidate.objects.select_for_update()
            .select_related("left_entity", "right_entity")
            .get(pk=candidate.pk)
        )
        if candidate.status != MatchCandidate.Status.PENDING:
            raise EntityResolutionError("Match candidate has already been decided.")
        decision = MatchDecision.objects.create(
            candidate=candidate,
            outcome=outcome,
            decided_by=decided_by,
            policy_version=candidate.policy_version,
            reason=reason,
        )
        status_by_outcome = {
            MatchDecision.Outcome.BIND: MatchCandidate.Status.ACCEPTED,
            MatchDecision.Outcome.REJECT: MatchCandidate.Status.REJECTED,
            MatchDecision.Outcome.ABSTAIN: MatchCandidate.Status.ABSTAINED,
        }
        candidate.status = status_by_outcome[outcome]
        candidate.save(update_fields=["status", "updated_at"])
        if outcome == MatchDecision.Outcome.BIND:
            source, target = self._canonical_pair(candidate)
            merge_event = self.merge(
                source=source,
                target=target,
                method=self._merge_method(decided_by),
                reason=reason,
            )
            decision.decision_data = {
                "merge_event_id": str(merge_event.id),
                "source_entity_id": str(source.id),
                "canonical_entity_id": str(target.id),
            }
            decision.save(update_fields=["decision_data", "updated_at"])
        return decision

    def _canonical_pair(self, candidate: MatchCandidate) -> tuple[Entity, Entity]:
        left = self.resolve(candidate.left_entity)
        right = self.resolve(candidate.right_entity)
        if left.pk == right.pk:
            raise EntityResolutionError("Candidate entities already resolve together.")
        if left.kind != right.kind:
            raise EntityResolutionError("Cannot bind entities of different kinds.")

        counts = {left.pk: 0, right.pk: 0}
        from apps.users.models import UserSubject

        left_ids = self.cluster_ids(left)
        right_ids = self.cluster_ids(right)
        for row in (
            UserSubject.objects.filter(entity_id__in=left_ids | right_ids)
            .values("entity_id")
            .annotate(total=Count("id"))
        ):
            if row["entity_id"] in left_ids:
                counts[left.pk] += row["total"]
            else:
                counts[right.pk] += row["total"]

        left_safety = self._safety_rank(left)
        right_safety = self._safety_rank(right)
        if left_safety != right_safety:
            target = left if left_safety > right_safety else right
        elif bool(counts[left.pk]) != bool(counts[right.pk]):
            target = left if counts[left.pk] else right
        else:
            target = min(
                (left, right), key=lambda item: (item.created_at, str(item.pk))
            )
        source = right if target.pk == left.pk else left
        return source, target

    def _ensure_no_user_library_conflict(
        self, *, source: Entity, target: Entity
    ) -> None:
        from apps.users.models import UserSubject

        source_users = UserSubject.objects.filter(
            entity_id__in=self.cluster_ids(source)
        ).values("user_id")
        if UserSubject.objects.filter(
            entity_id__in=self.cluster_ids(target),
            user_id__in=source_users,
        ).exists():
            raise EntityResolutionError(
                "Cannot merge entities with conflicting user library entries."
            )

    def _merge_snapshot(self, *, source: Entity, target: Entity) -> dict:
        from apps.users.models import UserSubject

        cluster_ids = self.cluster_ids(source) | self.cluster_ids(target)
        entries = list(
            UserSubject.objects.filter(entity_id__in=cluster_ids)
            .order_by("id")
            .values("id", "user_id", "entity_id")
        )
        return {
            "version": 1,
            "source_cluster_ids": sorted(
                str(value) for value in self.cluster_ids(source)
            ),
            "target_cluster_ids": sorted(
                str(value) for value in self.cluster_ids(target)
            ),
            "user_library_entries": [
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "entity_id": str(row["entity_id"]),
                }
                for row in entries
            ],
        }

    @staticmethod
    def _merge_method(decided_by: str) -> str:
        if decided_by == "ai_policy":
            return MergeEvent.Method.AI_POLICY
        if decided_by == "manual":
            return MergeEvent.Method.MANUAL
        return MergeEvent.Method.RULE

    @staticmethod
    def _safety_rank(entity: Entity) -> tuple[int, bool, int]:
        visibility_rank = {
            Entity.Visibility.PUBLIC: 0,
            Entity.Visibility.AUTHENTICATED: 1,
            Entity.Visibility.RESTRICTED: 2,
        }
        return (
            visibility_rank[entity.visibility],
            entity.audience == Entity.Audience.ADULT,
            entity.spoiler_level,
        )


entity_resolution_service = EntityResolutionService()
