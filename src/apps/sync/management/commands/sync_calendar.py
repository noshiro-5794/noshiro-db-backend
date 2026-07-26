import json

from django.core.management.base import BaseCommand

from apps.sync.services.calendar_service import calendar_sync_service


class Command(BaseCommand):
    help = "Sync Bangumi daily anime calendar"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-subject-details",
            action="store_true",
            help="Only sync calendar entries and subject base data.",
        )

    def handle(self, *args, **options):
        result = calendar_sync_service.sync_calendar(
            sync_subject_details=not options["skip_subject_details"],
            verbose=True,
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
