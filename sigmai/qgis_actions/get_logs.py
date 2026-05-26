from __future__ import annotations

from typing import Any


def handle(params: dict[str, Any], context: dict[str, Any]):
    tail = int(params.get("tail", 200))
    tail = max(1, min(tail, 1000))
    logger = context.get("logger")
    records = logger.tail(tail) if logger else []
    return {"logs": records, "tail": tail}
