from django.core.management.base import BaseCommand

from apps.sync.tasks.scheduler import SyncScheduler


class Command(BaseCommand):
    help = "Run full sync scheduler"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            nargs="+",
            type=str,
            help="Reset specific tasks (e.g. Character Episode)",
        )

    def handle(self, *args, **options):
        scheduler = SyncScheduler()
        reset_tasks = options.get("reset")
        scheduler.run_all(reset_tasks=reset_tasks)
