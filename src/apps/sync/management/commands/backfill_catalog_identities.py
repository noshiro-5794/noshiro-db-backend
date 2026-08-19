from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.sync.services.catalog_identity_backfill import (
    BACKFILL_CONFIGS,
    CatalogIdentityBackfillError,
    CatalogIdentityBackfillService,
)


class Command(BaseCommand):
    help = "Backfill source records and external identities from legacy source fields."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--entity",
            choices=["all", *BACKFILL_CONFIGS],
            default="all",
        )
        parser.add_argument("--batch-size", type=int, default=5000)
        parser.add_argument(
            "--start-after",
            help="Resume after this primary key; only valid for one entity.",
        )
        parser.add_argument("--max-rows", type=int)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        service = CatalogIdentityBackfillService(write=self.stdout.write)
        try:
            service.run(
                entity=options["entity"],
                batch_size=options["batch_size"],
                start_after=options["start_after"],
                max_rows=options["max_rows"],
                dry_run=options["dry_run"],
            )
        except CatalogIdentityBackfillError as exc:
            raise CommandError(str(exc)) from exc
