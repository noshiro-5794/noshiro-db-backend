import json

from django.core.management.base import BaseCommand, CommandError

from apps.sync.exceptions import SyncException
from apps.sync.services.incremental_sync_service import incremental_sync_service


class Command(BaseCommand):
    help = "Run incremental sync windows"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            help="Override the configured incremental batch size.",
        )
        parser.add_argument(
            "--task",
            type=str,
            choices=list(incremental_sync_service.TASKS.keys()),
            help="Run one incremental task. By default all incremental tasks run in order.",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Print current incremental sync status without running.",
        )
        parser.add_argument(
            "--unlock-running",
            action="store_true",
            help="Mark stale running incremental tasks as failed.",
        )

    def handle(self, *args, **options):
        if options["unlock_running"]:
            result = incremental_sync_service.unlock_running(
                task_name=options.get("task"),
            )
        elif options["status"]:
            result = incremental_sync_service.get_status()
        else:
            try:
                if options.get("task"):
                    result = incremental_sync_service.sync_task(
                        task_name=options["task"],
                        batch_size=options.get("batch_size"),
                        verbose=True,
                    )
                else:
                    result = incremental_sync_service.sync_all(
                        batch_size=options.get("batch_size"),
                        verbose=True,
                    )
            except SyncException as exc:
                raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, indent=2))
