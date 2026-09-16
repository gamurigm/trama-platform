"""Normalización y redacción de datos de observabilidad."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_REDACTED = "[REDACTED]"
_SECRET_KEY = re.compile(
    r"(?:token|secret|password|passwd|cookie|authorization|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.+?-----END [^-]*PRIVATE KEY-----",
    re.IGNORECASE | re.DOTALL,
)
_MAX_METADATA_ITEMS = 50
_MAX_STRING = 1000
_MAX_DEPTH = 3


def _redact_text(value: str) -> str:
    value = _BEARER.sub(r"\1" + _REDACTED, value)
    return _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", value)


def _sanitize_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= _MAX_DEPTH:
        return "[TRUNCATED]"
    if isinstance(value, str):
        return _redact_text(value[:_MAX_STRING])
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_METADATA_ITEMS:
                break
            safe_key = str(key)[:100]
            sanitized[safe_key] = (
                _REDACTED
                if _SECRET_KEY.search(safe_key)
                else _sanitize_value(item, depth=depth + 1)
            )
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item, depth=depth + 1) for item in value[:_MAX_METADATA_ITEMS]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _redact_text(str(value)[:_MAX_STRING])


def sanitize_message(message: str, metadata: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    """Redact secrets and bound log payloads before durable storage."""

    safe_metadata = _sanitize_value(metadata)
    return _redact_text(message[:4000]), safe_metadata
