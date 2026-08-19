from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.sync.services.relation_evidence_backfill import (
    BACKFILL_CONFIGS,
    RelationEvidenceBackfillError,
    RelationEvidenceBackfillService,
)


class Command(BaseCommand):
    help = (
        "Backfill Bangumi evidence for relations created by the legacy "
        "Bangumi-only sync pipeline."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--relation-type",
            choices=["all", *BACKFILL_CONFIGS],
            default="all",
        )
        parser.add_argument("--batch-size", type=int, default=5000)
        parser.add_argument(
            "--start-after",
            type=int,
            help="Resume after this primary key; only valid for one relation type.",
        )
        parser.add_argument("--max-rows", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        service = RelationEvidenceBackfillService(write=self.stdout.write)
        try:
            service.run(
                relation_type=options["relation_type"],
                batch_size=options["batch_size"],
                start_after=options["start_after"],
                max_rows=options["max_rows"],
                dry_run=options["dry_run"],
            )
        except RelationEvidenceBackfillError as exc:
            raise CommandError(str(exc)) from exc
