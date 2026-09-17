import json

from django.core.management.base import BaseCommand

from apps.sync.services.provider_raw_state_service import (
    provider_raw_state_service,
)


class Command(BaseCommand):
    help = (
        "Audit provider raw-payload completeness. Dry-run by default; with "
        "--apply it classifies records as raw/slim/stub/legacy and repairs "
        "the stale MAL Jikan record."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist classifications and repairs.",
        )
        parser.add_argument(
            "--repair-mal-legacy",
            action="store_true",
            help="Mark stale MAL Jikan records missing/legacy.",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        result = {
            "classification": provider_raw_state_service.classify(apply=apply),
            "report": provider_raw_state_service.report(),
            "superseded_anilist_seasons": (
                provider_raw_state_service.repair_superseded_anilist_seasons(
                    apply=apply
                )
            ),
        }
        if options["repair_mal_legacy"]:
            result["mal_legacy"] = provider_raw_state_service.repair_mal_legacy(
                apply=apply
            )
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, indent=2))
