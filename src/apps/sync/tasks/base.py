import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import close_old_connections

from apps.sync.models import SyncState
from apps.sync.providers.bangumi import BangumiAPIError
from apps.sync.tasks.progress import ProgressRecorder

logger = logging.getLogger(__name__)


class BaseSyncTask:
    TASK_NAME = None
    MAX_WORKERS = 5
    SHARD_SIZE = 16384
    MAX_RETRY = 3
    REFRESH_INTERVAL = 50

    def run(self, handler: Callable[[int], None], start: int, end: int) -> None:
        shards = self._build_shards(start, end)
        with ThreadPoolExecutor(
            max_workers=self.MAX_WORKERS,
            thread_name_prefix=f"sync-{self.TASK_NAME}",
        ) as executor:
            futures = [
                executor.submit(self._run_shard, handler, shard) for shard in shards
            ]
            for future in as_completed(futures):
                future.result()

    def _run_shard(self, handler, shard: tuple[int, int]) -> None:
        close_old_connections()
        try:
            start, end = shard
            shard_name = f"{start}-{end}"

            state, _ = SyncState.objects.get_or_create(
                task_name=self.TASK_NAME,
                shard=shard_name,
                defaults={
                    "current_id": max(0, start - 1),
                    "end_id": end,
                    "status": SyncState.Status.RUNNING,
                },
            )

            SyncState.objects.filter(task_name=self.TASK_NAME, shard=shard_name).update(
                status=SyncState.Status.RUNNING,
                end_id=end,
            )

            recorder = ProgressRecorder(
                self.TASK_NAME,
                shard_name,
                initial_fail_count=state.fail_count,
            )

            current = max(state.current_id + 1, start)
            step = 0

            try:
                while current <= end:
                    if step % self.REFRESH_INTERVAL == 0:
                        state.refresh_from_db()
                        if state.status != SyncState.Status.RUNNING:
                            return

                    success = self._safe_handle(handler, current)

                    if not success:
                        recorder.record_fail(current)

                    recorder.flush(current)

                    current += 1
                    step += 1

                recorder.finish(end)

                SyncState.objects.filter(
                    task_name=self.TASK_NAME,
                    shard=shard_name,
                ).update(status=SyncState.Status.FINISHED)
            except Exception:
                SyncState.objects.filter(
                    task_name=self.TASK_NAME,
                    shard=shard_name,
                ).update(status=SyncState.Status.FAILED)
                raise
        finally:
            close_old_connections()

    def _safe_handle(self, handler: Callable[[int], None], id_: int) -> bool:
        for attempt in range(1, self.MAX_RETRY + 1):
            try:
                handler(id_)
                return True
            except BangumiAPIError as exc:
                if exc.is_not_found:
                    return True
                if attempt == self.MAX_RETRY:
                    logger.warning(
                        "Full sync provider request failed after retries",
                        extra={"task_name": self.TASK_NAME, "entity_id": id_},
                        exc_info=True,
                    )
            except Exception:
                if attempt == self.MAX_RETRY:
                    logger.exception(
                        "Full sync entity failed after retries",
                        extra={"task_name": self.TASK_NAME, "entity_id": id_},
                    )
        return False

    def _build_shards(self, start: int, end: int) -> list[tuple[int, int]]:
        shards = []
        cur = start

        while cur <= end:
            shard_end = min(cur + self.SHARD_SIZE - 1, end)
            shards.append((cur, shard_end))
            cur = shard_end + 1

        return shards
