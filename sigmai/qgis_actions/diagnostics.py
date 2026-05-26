from __future__ import annotations

from typing import Any

from ..logging_utils import filter_error_records


def get_recent_errors(params: dict[str, Any], context: dict[str, Any]):
    tail = max(1, min(int(params.get("tail", 200)), 1000))
    logger = context.get("logger")
    records = logger.tail(tail) if logger else []
    return {"errors": filter_error_records(records), "tail": tail}
