from __future__ import annotations

from typing import Any


def filter_error_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors = []
    for record in records:
        event = str(record.get("event", "")).lower()
        if "error" in event or "crash" in event or record.get("ok") is False:
            errors.append(record)
    return errors
