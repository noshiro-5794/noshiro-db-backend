import json

from django.core.management.base import BaseCommand

from apps.sync.services.anilist_season_service import (
    anilist_season_service,
    current_anilist_season,
)


class Command(BaseCommand):
    help = "Fetch and persist the current AniList season anime and schedules."

    def add_arguments(self, parser):
        parser.add_argument(
            "--season",
            choices=("WINTER", "SPRING", "SUMMER", "FALL"),
            default=None,
            help="Override the broadcast season (defaults to the local quarter).",
        )
        parser.add_argument("--season-year", type=int, default=None)
        parser.add_argument("--page-size", type=int, default=50)
        parser.add_argument("--max-pages", type=int, default=40)

    def handle(self, *args, **options):
        if options["season"]:
            season = options["season"]
            _, default_year = current_anilist_season()
            season_year = options["season_year"] or default_year
            result = anilist_season_service.sync_season(
                season=season,
                season_year=season_year,
                page_size=options["page_size"],
                max_pages=options["max_pages"],
            )
        else:
            result = anilist_season_service.sync_current_airing(
                page_size=options["page_size"],
                max_pages=options["max_pages"],
            )
        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, indent=2))
