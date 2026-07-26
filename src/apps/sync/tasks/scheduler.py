import logging
import threading
import time

from apps.sync.models import SyncError, SyncState
from apps.sync.tasks.full_sync import (
    FullCharacterSyncTask,
    FullCharRelSyncTask,
    FullEpisodeSyncTask,
    FullStaffSyncTask,
    FullStfRelSyncTask,
    FullSubjectSyncTask,
    FullSubjRelSyncTask,
)
from apps.sync.tasks.progress import get_task_progress

logger = logging.getLogger(__name__)


class SyncScheduler:
    TASKS = [
        ("full_subject", FullSubjectSyncTask),
        ("full_episode", FullEpisodeSyncTask),
        ("full_subject_subject_relation", FullSubjRelSyncTask),
        ("full_subject_staff_relation", FullStfRelSyncTask),
        ("full_subject_character_relation", FullCharRelSyncTask),
        ("full_character", FullCharacterSyncTask),
        ("full_staff", FullStaffSyncTask),
    ]

    PROGRESS_INTERVAL = 2

    def run_all(self, reset_tasks=None) -> None:
        logger.info("Full sync started")
        if reset_tasks:
            for task in reset_tasks:
                self._reset_task(task)
        started = False
        for name, task_cls in self.TASKS:
            states = SyncState.objects.filter(task_name=name)
            if not started:
                if states.exists() and all(
                    state.status == SyncState.Status.FINISHED for state in states
                ):
                    logger.info("Full sync phase skipped", extra={"task_name": name})
                    continue
                else:
                    started = True
            self._run_phase(name, task_cls)
        logger.info("Full sync completed")

    def _reset_task(self, task_name: str):
        logger.info("Full sync phase reset", extra={"task_name": task_name})

        SyncState.objects.filter(task_name=task_name).delete()
        SyncError.objects.filter(task_name=task_name).delete()

    def _run_phase(self, name, task_cls):
        logger.info("Full sync phase started", extra={"task_name": name})
        start_time = time.monotonic()

        stop_event = threading.Event()
        monitor = threading.Thread(
            target=self._progress_monitor,
            args=(name, stop_event),
            daemon=True,
        )
        monitor.start()
        try:
            task = task_cls()
            task.run_task()
        except Exception:
            logger.exception("Full sync phase failed", extra={"task_name": name})
            raise
        finally:
            stop_event.set()
            monitor.join()

        cost = time.monotonic() - start_time
        logger.info(
            "Full sync phase completed",
            extra={"task_name": name, "duration_seconds": cost},
        )

    def _progress_monitor(self, task_name, stop_event):
        while not stop_event.is_set():
            progress = get_task_progress(task_name)
            percent = progress["progress"] * 100
            logger.info(
                "Full sync progress",
                extra={"task_name": task_name, "progress_percent": percent},
            )
            stop_event.wait(self.PROGRESS_INTERVAL)
