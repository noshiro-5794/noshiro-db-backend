from django.core.management.base import BaseCommand, CommandError

from apps.sync.services.anilist_service import anilist_import_service


class Command(BaseCommand):
    help = "Import one AniList anime media entry into the knowledge graph."

    def add_arguments(self, parser):
        parser.add_argument("anilist_id", type=int)

    def handle(self, *args, **options):
        try:
            entity = anilist_import_service.import_media(options["anilist_id"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported AniList {options['anilist_id']} as {entity.id}"
            )
        )
