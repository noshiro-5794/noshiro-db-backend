import os
import time

from celery import Celery
from celery.signals import task_postrun, task_prerun

from shared.observability import clear_context, set_task_context
from shared.observability.metrics import record_task_event

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("config")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

_task_started_at: dict[str, float] = {}


@task_prerun.connect
def bind_task_context(task_id, task, args, kwargs, **_):
    set_task_context(task_id=task_id, job_id=(kwargs or {}).get("job_id"))
    _task_started_at[task_id] = time.monotonic()


@task_postrun.connect
def record_task_finish(task_id, task, state, retval, **_):
    started_at = _task_started_at.pop(task_id, None)
    duration_ms = (
        round((time.monotonic() - started_at) * 1000, 2)
        if started_at is not None
        else None
    )
    record_task_event(
        event="completed",
        task_name=task.name,
        task_id=task_id,
        state=state,
        duration_ms=duration_ms,
    )
    clear_context()
