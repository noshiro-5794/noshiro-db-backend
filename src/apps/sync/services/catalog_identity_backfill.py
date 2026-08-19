from collections.abc import Callable
from dataclasses import dataclass

from django.db import models

from apps.index.models import Character, Episode, Staff, Subject
from apps.sync.providers.bangumi import (
    BANGUMI_CHARACTER_NAMESPACE,
    BANGUMI_EPISODE_NAMESPACE,
    BANGUMI_PERSON_NAMESPACE,
    BANGUMI_SUBJECT_NAMESPACE,
)
from apps.sync.providers.contracts import SourceNamespaceSpec
from apps.sync.services.source_record_service import (
    source_identity_service,
    source_record_service,
)


@dataclass(frozen=True, slots=True)
class BackfillConfig:
    model: type[models.Model]
    legacy_source: str
    namespace: SourceNamespaceSpec
    bind_method: str


BACKFILL_CONFIGS = {
    "subject": BackfillConfig(
        model=Subject,
        legacy_source="bangumi_subject",
        namespace=BANGUMI_SUBJECT_NAMESPACE,
        bind_method="bind_subjects",
    ),
    "episode": BackfillConfig(
        model=Episode,
        legacy_source="bangumi_episode",
        namespace=BANGUMI_EPISODE_NAMESPACE,
        bind_method="bind_episodes",
    ),
    "staff": BackfillConfig(
        model=Staff,
        legacy_source="bangumi_persons",
        namespace=BANGUMI_PERSON_NAMESPACE,
        bind_method="bind_staff_members",
    ),
    "character": BackfillConfig(
        model=Character,
        legacy_source="bangumi_character",
        namespace=BANGUMI_CHARACTER_NAMESPACE,
        bind_method="bind_characters",
    ),
}


class CatalogIdentityBackfillError(RuntimeError):
    """Raised when legacy catalog identities cannot be backfilled."""


class CatalogIdentityBackfillService:
    def __init__(self, *, write: Callable[[str], None] | None = None) -> None:
        self._write = write or (lambda _message: None)

    def run(
        self,
        *,
        entity: str = "all",
        batch_size: int = 5000,
        start_after: str | None = None,
        max_rows: int | None = None,
        dry_run: bool = False,
    ) -> None:
        if batch_size < 1:
            raise CatalogIdentityBackfillError(
                "--batch-size must be greater than zero."
            )
        if max_rows is not None and max_rows < 1:
            raise CatalogIdentityBackfillError("--max-rows must be greater than zero.")
        if entity == "all" and start_after is not None:
            raise CatalogIdentityBackfillError(
                "--start-after requires a specific --entity."
            )

        selected = (
            BACKFILL_CONFIGS if entity == "all" else {entity: BACKFILL_CONFIGS[entity]}
        )
        for entity_name, config in selected.items():
            self._preflight(entity_name=entity_name, config=config)

        for entity_name, config in selected.items():
            self._backfill(
                entity_name=entity_name,
                config=config,
                batch_size=batch_size,
                start_after=start_after,
                max_rows=max_rows,
                dry_run=dry_run,
            )

    def _preflight(self, *, entity_name: str, config: BackfillConfig) -> None:
        unknown_sources = list(
            config.model.objects.exclude(info_source=config.legacy_source)
            .values_list("info_source", flat=True)
            .distinct()[:20]
        )
        if unknown_sources:
            raise CatalogIdentityBackfillError(
                f"{entity_name} contains unsupported legacy sources: {unknown_sources}"
            )
        if config.model.objects.filter(id_source="").exists():
            raise CatalogIdentityBackfillError(
                f"{entity_name} contains an empty id_source."
            )

    def _backfill(
        self,
        *,
        entity_name: str,
        config: BackfillConfig,
        batch_size: int,
        start_after: str | None,
        max_rows: int | None,
        dry_run: bool,
    ) -> None:
        queryset = config.model.objects.filter(info_source=config.legacy_source)
        if start_after is not None:
            pk_value = config.model._meta.pk.to_python(start_after)
            queryset = queryset.filter(pk__gt=pk_value)
        queryset = queryset.order_by("pk")

        if dry_run:
            count = queryset.count()
            if max_rows is not None:
                count = min(count, max_rows)
            self._write(f"{entity_name}: would process {count} rows")
            return

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
            rows = list(batch_queryset.values_list("pk", "id_source")[:remaining])
            if not rows:
                break

            records = source_record_service.ensure_legacy_records(
                namespace_spec=config.namespace,
                external_ids=[external_id for _pk, external_id in rows],
            )
            targets = config.model.objects.in_bulk([pk for pk, _external_id in rows])
            bindings = [(targets[pk], records[external_id]) for pk, external_id in rows]
            bind = getattr(source_identity_service, config.bind_method)
            created = bind(
                bindings=bindings,
                match_method="legacy",
                make_primary=True,
            )

            processed += len(rows)
            last_pk = rows[-1][0]
            self._write(
                f"{entity_name}: processed={processed} "
                f"created={created} last_pk={last_pk}"
            )

        self._write(f"{entity_name}: completed processed={processed} last_pk={last_pk}")
