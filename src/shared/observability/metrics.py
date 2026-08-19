import logging

logger = logging.getLogger("noshiro.tasks")


def record_task_event(
    *,
    event: str,
    task_name: str,
    task_id: str | None = None,
    state: str | None = None,
    duration_ms: float | None = None,
    **extra,
) -> None:
    logger.info(
        "Celery task event",
        extra={
            "event": event,
            "task_name": task_name,
            "task_id": task_id,
            "state": state,
            "duration_ms": duration_ms,
            **extra,
        },
    )
