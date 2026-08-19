from django.core.management.base import BaseCommand, CommandError

from apps.sync.exceptions import SyncOperationError
from apps.sync.services.manual_sync_service import manual_subject_sync_service


class Command(BaseCommand):
    help = "Sync one Bangumi subject and its direct sections"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--uuid",
            type=str,
            help="Local Subject UUID to resync.",
        )
        group.add_argument(
            "--bangumi-id",
            type=int,
            help="Bangumi subject ID to sync.",
        )

    def handle(self, *args, **options):
        try:
            if options["uuid"]:
                result = manual_subject_sync_service.sync_by_uuid(
                    subject_id=options["uuid"],
                )
            else:
                result = manual_subject_sync_service.sync_by_bangumi_id(
                    bangumi_id=options["bangumi_id"],
                )
        except SyncOperationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Subject sync finished."))
        for key, value in result.items():
            self.stdout.write(f"{key}: {value}")
