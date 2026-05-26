from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from .permissions import SCHEMA_VERSION, permission_for
from .validators import ValidationError, validate_command


Handler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class CommandRegistry:
    def __init__(self, qgis_context: dict[str, Any]):
        self._handlers: dict[str, Handler] = {}
        self._qgis_context = qgis_context

    def register(self, action: str, handler: Handler) -> None:
        self._handlers[action] = handler

    def actions(self) -> list[str]:
        return sorted(self._handlers)

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        action = command.get("action", "unknown")
        request_id = command.get("request_id", command.get("id", ""))
        try:
            normalized = validate_command(command, unsafe_developer_mode=bool(self._qgis_context.get("unsafe_developer_mode", False)))
            action = normalized["action"]
            request_id = normalized.get("request_id", "")
            handler = self._handlers.get(action)
            if handler is None:
                raise ValidationError("ACTION_NOT_ALLOWED", f"No handler registered for action: {action}")
            handler_context = dict(self._qgis_context)
            handler_context["dry_run"] = normalized.get("dry_run", False)
            handler_context["request_id"] = request_id
            handler_context["registered_actions"] = sorted(self._handlers)
            handler_context["command_executor"] = self.execute
            data = handler(normalized.get("params", {}), handler_context)
            return make_response(True, action, data, [], [], started, self._qgis_context, request_id)
        except ValidationError as exc:
            return make_response(
                False,
                action,
                None,
                [],
                [{"code": exc.code, "message": str(exc), "details": exc.details}],
                started,
                self._qgis_context,
                request_id,
            )
        except Exception as exc:
            return make_response(
                False,
                action,
                None,
                [],
                [{"code": "INTERNAL_ERROR", "message": str(exc), "details": {"type": type(exc).__name__}}],
                started,
                self._qgis_context,
                request_id,
            )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def make_response(
    ok: bool,
    action: str,
    data: Any,
    warnings: list[str],
    errors: list[dict[str, Any]],
    started: float,
    qgis_context: dict[str, Any],
    request_id: str = "",
) -> dict[str, Any]:
    duration_ms = int((time.perf_counter() - started) * 1000) if started > 0 else 0
    permission = permission_for(action)
    meta: dict[str, Any] = {
        "timestamp": utc_now(),
        "duration_ms": duration_ms,
        "permission_level": permission.permission_level if permission else "unknown",
    }
    qgis_version = qgis_context.get("qgis_version")
    if qgis_version:
        meta["qgis_version"] = qgis_version
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "ok": ok,
        "action": action,
        "data": data,
        "warnings": warnings,
        "errors": errors,
        "meta": meta,
    }
