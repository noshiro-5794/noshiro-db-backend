from django.core.management.base import BaseCommand, CommandError

from apps.sync.services.vndb_service import vndb_import_service


class Command(BaseCommand):
    help = "Import one VNDB work and its releases, characters, staff, and tags."

    def add_arguments(self, parser):
        parser.add_argument("vndb_id")
        parser.add_argument("--without-related", action="store_true")

    def handle(self, *args, **options):
        vndb_id = options["vndb_id"]
        try:
            entity = vndb_import_service.import_work(
                vndb_id=vndb_id,
                include_related=not options["without_related"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Imported {vndb_id} as {entity.id}"))
