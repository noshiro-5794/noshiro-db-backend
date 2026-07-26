import time
from collections import defaultdict

from django.db.models import F
from django.utils import timezone

from apps.sync.models import SyncError, SyncState


class ProgressRecorder:
    FLUSH_INTERVAL = 2
    ERROR_FLUSH_SIZE = 200

    def __init__(
        self,
        task_name: str,
        shard: str,
        *,
        initial_fail_count: int = 0,
    ) -> None:
        self.task_name = task_name
        self.shard = shard

        self.fail_count = initial_fail_count
        self.error_buffer: defaultdict[int, int] = defaultdict(int)
        self.last_flush = time.monotonic()

    def record_fail(self, id_: int) -> None:
        self.fail_count += 1
        self.error_buffer[id_] += 1

        if len(self.error_buffer) >= self.ERROR_FLUSH_SIZE:
            self.flush_errors()

    def flush(self, current_id: int, force: bool = False) -> None:
        now = time.monotonic()

        if not force and (now - self.last_flush < self.FLUSH_INTERVAL):
            return

        SyncState.objects.filter(task_name=self.task_name, shard=self.shard).update(
            current_id=current_id,
            fail_count=self.fail_count,
        )

        self.flush_errors()
        self.last_flush = now

    def flush_errors(self) -> None:
        if not self.error_buffer:
            return

        now = timezone.now()

        for entity_id, count in self.error_buffer.items():
            error, created = SyncError.objects.get_or_create(
                task_name=self.task_name,
                entity_id=entity_id,
                defaults={
                    "retry_count": count,
                },
            )
            if not created:
                SyncError.objects.filter(pk=error.pk).update(
                    retry_count=F("retry_count") + count,
                    last_occurred_at=now,
                )

        self.error_buffer.clear()

    def finish(self, current_id: int) -> None:
        self.flush(current_id, force=True)


def parse_shard(shard: str) -> tuple[int, int]:
    start, end = shard.split("-")
    return int(start), int(end)


def get_task_progress(task_name: str) -> dict:
    states = SyncState.objects.filter(task_name=task_name)

    total = 0
    done = 0

    for s in states:
        start, end = parse_shard(s.shard)

        total += end - start + 1
        done += max(0, min(s.current_id, end) - start + 1)

    return {
        "task": task_name,
        "progress": done / total if total else 0,
        "shards": states.count(),
    }
