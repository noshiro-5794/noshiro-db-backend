import json

from django.core.management.base import BaseCommand

from apps.sync.services.provider_stub_backfill_service import (
    provider_stub_backfill_service,
)


class Command(BaseCommand):
    help = (
        "Report provider stub records and backfill supported ones. Currently "
        "AniList anime stubs are fetched through the official GraphQL API."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Fetch and persist supported stub records.",
        )
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        result = provider_stub_backfill_service.backfill(
            apply=options["apply"],
            limit=options["limit"],
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, indent=2))
