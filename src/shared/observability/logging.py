import json
import logging
from datetime import UTC, datetime
from typing import Any

from shared.observability.context import get_context

_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__) | {
    "asctime",
    "message",
}
_SENSITIVE_FIELDS = {
    "authorization",
    "code",
    "cookie",
    "email",
    "password",
    "raw_payload",
    "secret",
    "token",
}
_SENSITIVE_SUFFIXES = ("_password", "_secret", "_token")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
            if not _is_sensitive(str(key))
        }
    if isinstance(value, list | tuple | set):
        return [_json_value(item) for item in value]
    return str(value)


def _is_sensitive(key: str) -> bool:
    normalized = key.lower()
    return normalized in _SENSITIVE_FIELDS or normalized.endswith(_SENSITIVE_SUFFIXES)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **get_context(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
                continue
            if _is_sensitive(key):
                continue
            payload[key] = _json_value(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
