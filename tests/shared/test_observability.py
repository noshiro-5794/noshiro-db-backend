import logging

from shared.observability import clear_context, set_task_context
from shared.observability.logging import JsonFormatter, _is_sensitive, _json_value
from shared.observability.metrics import record_task_event


class TestContext:
    def test_set_and_clear_context(self) -> None:
        set_task_context(task_id="task-1", job_id="job-1")
        # Context is set; clearing should not raise
        clear_context()

    def test_clear_without_set_does_not_raise(self) -> None:
        clear_context()


class TestMetrics:
    def test_record_task_event_does_not_raise(self) -> None:
        record_task_event(
            event="completed",
            task_name="test_task",
            task_id="task-1",
            state="SUCCESS",
            duration_ms=100.0,
        )


class TestLogging:
    def test_is_sensitive_detects_password(self) -> None:
        assert _is_sensitive("password") is True
        assert _is_sensitive("user_password") is True
        assert _is_sensitive("username") is False

    def test_json_value_handles_dict(self) -> None:
        result = _json_value({"key": "val", "password": "secret"})
        assert result["key"] == "val"
        assert "password" not in result

    def test_json_value_handles_list(self) -> None:
        result = _json_value([1, "two", 3.0])
        assert result == [1, "two", 3.0]

    def test_formatter_includes_exception(self) -> None:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="boom",
            args=(),
            exc_info=None,
        )
        try:
            raise ValueError("test error")
        except ValueError:
            record.exc_info = logging.sys.exc_info()
        payload = formatter.format(record)
        assert "exception" in payload
        assert "test error" in payload
