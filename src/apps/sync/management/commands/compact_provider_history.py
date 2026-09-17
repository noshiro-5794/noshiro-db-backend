import json

from django.core.management.base import BaseCommand

from apps.sync.services.provider_snapshot_retention_service import (
    provider_snapshot_retention_service,
)


class Command(BaseCommand):
    help = (
        "Report or apply snapshot retention. Dry-run by default; --apply keeps "
        "only the latest revision for current-only snapshot namespaces."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete compactable revisions and observations.",
        )

    def handle(self, *args, **options):
        result = provider_snapshot_retention_service.compact(
            apply=options["apply"],
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, indent=2))
