from collections.abc import Callable
from dataclasses import dataclass

from django.db import models
from django.db.models import Exists, OuterRef

from apps.index.models import (
    CatalogSource,
    RelationEvidence,
    SubjectCharacterActorRelation,
    SubjectCharacterRelation,
    SubjectStaffRelation,
    SubjectSubjectRelation,
)
from apps.sync.providers.bangumi import (
    BANGUMI_SOURCE,
    BANGUMI_SUBJECT_NAMESPACE,
)
from apps.sync.services.source_record_service import source_record_service


@dataclass(frozen=True, slots=True)
class RelationBackfillConfig:
    model: type[models.Model]
    evidence_field: str


BACKFILL_CONFIGS = {
    "subject": RelationBackfillConfig(
        model=SubjectSubjectRelation,
        evidence_field="subject_relation",
    ),
    "staff": RelationBackfillConfig(
        model=SubjectStaffRelation,
        evidence_field="staff_relation",
    ),
    "character": RelationBackfillConfig(
        model=SubjectCharacterRelation,
        evidence_field="character_relation",
    ),
    "actor": RelationBackfillConfig(
        model=SubjectCharacterActorRelation,
        evidence_field="character_actor_relation",
    ),
}


class RelationEvidenceBackfillError(RuntimeError):
    """Raised when legacy relation evidence cannot be backfilled."""


class RelationEvidenceBackfillService:
    def __init__(self, *, write: Callable[[str], None] | None = None) -> None:
        self._write = write or (lambda _message: None)

    def run(
        self,
        *,
        relation_type: str = "all",
        batch_size: int = 5000,
        start_after: int | None = None,
        max_rows: int | None = None,
        dry_run: bool = False,
    ) -> None:
        if batch_size < 1:
            raise RelationEvidenceBackfillError(
                "--batch-size must be greater than zero."
            )
        if max_rows is not None and max_rows < 1:
            raise RelationEvidenceBackfillError("--max-rows must be greater than zero.")
        if relation_type == "all" and start_after is not None:
            raise RelationEvidenceBackfillError(
                "--start-after requires one --relation-type."
            )

        source = CatalogSource.objects.filter(slug=BANGUMI_SOURCE.slug).first()
        if source is None and not dry_run:
            source = source_record_service.get_or_create_namespace(
                BANGUMI_SUBJECT_NAMESPACE
            ).source

        selected = (
            BACKFILL_CONFIGS
            if relation_type == "all"
            else {relation_type: BACKFILL_CONFIGS[relation_type]}
        )
        for relation_name, config in selected.items():
            self._backfill(
                relation_name=relation_name,
                config=config,
                source=source,
                batch_size=batch_size,
                start_after=start_after,
                max_rows=max_rows,
                dry_run=dry_run,
            )

    def _backfill(
        self,
        *,
        relation_name: str,
        config: RelationBackfillConfig,
        source: CatalogSource | None,
        batch_size: int,
        start_after: int | None,
        max_rows: int | None,
        dry_run: bool,
    ) -> None:
        queryset = config.model.objects.order_by("pk")
        if source is not None:
            source_evidence = RelationEvidence.objects.filter(
                source=source,
                **{f"{config.evidence_field}_id": OuterRef("pk")},
            )
            queryset = queryset.annotate(
                has_source_evidence=Exists(source_evidence)
            ).filter(has_source_evidence=False)
        if start_after is not None:
            queryset = queryset.filter(pk__gt=start_after)

        if dry_run:
            count = queryset.count()
            if max_rows is not None:
                count = min(count, max_rows)
            self._write(f"{relation_name}: would process {count} rows")
            return

        if source is None:
            raise RelationEvidenceBackfillError(
                "Bangumi CatalogSource could not be initialized."
            )

        processed = 0
        last_pk = None
        while True:
            remaining = batch_size
            if max_rows is not None:
                remaining = min(remaining, max_rows - processed)
                if remaining <= 0:
                    break

            batch_queryset = queryset
            if last_pk is not None:
                batch_queryset = batch_queryset.filter(pk__gt=last_pk)
            relation_ids = list(batch_queryset.values_list("pk", flat=True)[:remaining])
            if not relation_ids:
                break

            RelationEvidence.objects.bulk_create(
                [
                    RelationEvidence(
                        source=source,
                        **{f"{config.evidence_field}_id": relation_id},
                    )
                    for relation_id in relation_ids
                ],
                batch_size=batch_size,
                ignore_conflicts=True,
            )
            processed += len(relation_ids)
            last_pk = relation_ids[-1]
            self._write(f"{relation_name}: processed={processed} last_pk={last_pk}")

        self._write(
            f"{relation_name}: completed processed={processed} last_pk={last_pk}"
        )
