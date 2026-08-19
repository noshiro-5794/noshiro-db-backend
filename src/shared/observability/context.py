from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_task_id: ContextVar[str | None] = ContextVar("task_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)


def get_context() -> dict[str, str]:
    values = {
        "request_id": _request_id.get(),
        "user_id": _user_id.get(),
        "task_id": _task_id.get(),
        "job_id": _job_id.get(),
    }
    return {key: value for key, value in values.items() if value}


def set_user_id(user_id: object | None) -> None:
    _user_id.set(str(user_id) if user_id is not None else None)


def set_task_context(*, task_id: str | None, job_id: str | None = None) -> None:
    _task_id.set(task_id)
    _job_id.set(job_id)


def clear_context() -> None:
    _request_id.set(None)
    _user_id.set(None)
    _task_id.set(None)
    _job_id.set(None)


@contextmanager
def bind_context(
    *,
    request_id: str | None = None,
    user_id: object | None = None,
    task_id: str | None = None,
    job_id: str | None = None,
) -> Iterator[None]:
    tokens = (
        (_request_id, _request_id.set(request_id)),
        (_user_id, _user_id.set(str(user_id) if user_id is not None else None)),
        (_task_id, _task_id.set(task_id)),
        (_job_id, _job_id.set(job_id)),
    )
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)
