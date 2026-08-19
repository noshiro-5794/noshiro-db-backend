import uuid
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.index.services.knowledge_backfill import (
    KnowledgeGraphBackfillError,
    KnowledgeGraphBackfillService,
)


class Command(BaseCommand):
    help = (
        "Backfill the source-neutral knowledge graph in checkpointed, idempotent "
        "batches without deleting legacy data."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--batch-size", type=int)
        parser.add_argument("--resume", type=uuid.UUID, metavar="RUN_ID")
        parser.add_argument("--status", type=uuid.UUID, metavar="RUN_ID")
        parser.add_argument(
            "--max-batches",
            type=int,
            help="Pause after this many committed batches; useful for rehearsals.",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        service = KnowledgeGraphBackfillService(write=self.stdout.write)
        try:
            service.run(
                batch_size=options["batch_size"],
                resume_id=options["resume"],
                status_id=options["status"],
                max_batches=options["max_batches"],
                dry_run=options["dry_run"],
            )
        except KnowledgeGraphBackfillError as exc:
            raise CommandError(str(exc)) from exc
