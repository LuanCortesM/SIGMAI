from __future__ import annotations

import json
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .capabilities import get_capabilities
from .command_registry import CommandRegistry, make_response
from .logging_utils import filter_error_records
from .qgis_actions import register_actions
from .security import DEFAULT_HOST, DEFAULT_PORT, is_localhost, validate_bearer_header
from .validators import ValidationError, validate_command


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class BridgeLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.last_error: str = ""

    def record(self, event: str, **payload: Any) -> None:
        entry = {"timestamp": _now(), "event": event, **payload}
        if not self._lock.acquire(timeout=0.5):
            self.last_error = "Log lock timeout."
            return
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self._lock.release()

    def tail(self, count: int) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        if not self._lock.acquire(timeout=0.5):
            return [{"timestamp": _now(), "event": "log_tail_failed", "error": "Log lock timeout."}]
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()[-count:]
        except Exception as exc:
            return [{"timestamp": _now(), "event": "log_tail_failed", "error": f"{type(exc).__name__}: {exc}"}]
        finally:
            self._lock.release()
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                records.append({"raw": line})
        return records


@dataclass
class QueuedCommand:
    command: dict[str, Any]
    client: str
    event: threading.Event
    response: dict[str, Any] | None = None
    enqueued_at: float = 0.0
    cancelled: bool = False


class SIGMAIServer:
    def __init__(
        self,
        iface: Any = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        token: str = "",
        log_dir: Path | None = None,
    ):
        self.iface = iface
        self.host = host
        self.port = int(port)
        self.token = token
        self.log_dir = log_dir or Path(__file__).resolve().parent / "logs"
        self.logger = BridgeLogger(self.log_dir / "sigmai.jsonl")
        self.qgis_version = self._qgis_version()
        self.queue: queue.Queue[QueuedCommand] = queue.Queue()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._timer = None
        self.unsafe_developer_mode = False
        self.registry = CommandRegistry(self._context())
        register_actions(self.registry)
        self.started_at = _now()
        self._current_command_lock = threading.Lock()
        self.current_command: dict[str, Any] | None = None
        self.last_command_error: dict[str, Any] | None = None

    def _context(self) -> dict[str, Any]:
        return {
            "iface": self.iface,
            "host": self.host,
            "port": self.port,
            "logger": self.logger,
            "qgis_version": self.qgis_version,
            "plugin_version": "0.1.0",
            "package_name": __package__.split(".")[0] if __package__ else "sigmai",
            "unsafe_developer_mode": self.unsafe_developer_mode,
        }

    def _qgis_version(self) -> str:
        try:
            from qgis.core import Qgis  # type: ignore

            return Qgis.QGIS_VERSION
        except Exception:
            return ""

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        if self.running:
            return
        if self.host != DEFAULT_HOST:
            raise ValueError("SIGMAI bridge only supports host 127.0.0.1.")

        handler = self._make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="SIGMAIHTTP", daemon=True)
        self._thread.start()
        self._start_qt_timer()
        self.logger.record("bridge_started", host=self.host, port=self.port)

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self.logger.record("bridge_stopped", host=self.host, port=self.port)

    def status(self) -> dict[str, Any]:
        current = self._current_command_snapshot()
        return {
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "log_path": str(self.logger.log_path),
            "started_at": self.started_at,
            "qgis_version": self.qgis_version,
            "plugin_version": "0.1.0",
            "package_name": __package__.split(".")[0] if __package__ else "sigmai",
            "registered_command_count": len(self.registry.actions()),
            "queue_size": self.queue.qsize(),
            "busy": current is not None,
            "current_command": current,
            "last_command_error": self.last_command_error,
            "logger_last_error": self.logger.last_error,
            "unsafe_developer_mode": self.unsafe_developer_mode,
        }

    def set_unsafe_developer_mode(self, enabled: bool) -> None:
        self.unsafe_developer_mode = bool(enabled)
        try:
            self.registry._qgis_context["unsafe_developer_mode"] = self.unsafe_developer_mode
        except Exception:
            pass
        self.logger.record("unsafe_developer_mode_changed", enabled=self.unsafe_developer_mode)

    def _current_command_snapshot(self) -> dict[str, Any] | None:
        with self._current_command_lock:
            return dict(self.current_command) if self.current_command else None

    def _set_current_command(self, item: QueuedCommand | None) -> None:
        with self._current_command_lock:
            if item is None:
                self.current_command = None
                return
            self.current_command = {
                "action": item.command.get("action"),
                "request_id": item.command.get("request_id", item.command.get("id", "")),
                "client": item.client,
                "started_at": _now(),
                "thread": threading.current_thread().name,
            }

    def _checkpoint(self, name: str, started: float, **payload: Any) -> None:
        self.logger.record(
            "command_checkpoint",
            checkpoint=name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            thread=threading.current_thread().name,
            thread_id=threading.get_ident(),
            **payload,
        )

    def _start_qt_timer(self) -> None:
        try:
            from qgis.PyQt.QtCore import QTimer  # type: ignore
        except Exception:
            self._timer = None
            return
        self._timer = QTimer()
        self._timer.timeout.connect(self.process_pending_commands)
        self._timer.start(100)

    def process_pending_commands(self) -> None:
        tick_started = time.perf_counter()
        processed = 0
        while processed < 1 and (time.perf_counter() - tick_started) < 0.05:
            try:
                item = self.queue.get_nowait()
            except queue.Empty:
                break
            if item.cancelled:
                self.logger.record("command_skipped_cancelled", action=item.command.get("action"), client=item.client)
                item.event.set()
                continue
            if item.enqueued_at and (time.perf_counter() - item.enqueued_at) > 120:
                self.logger.record("command_skipped_stale", action=item.command.get("action"), client=item.client)
                item.response = make_response(
                    False,
                    item.command.get("action", "unknown"),
                    None,
                    [],
                    [{"code": "COMMAND_QUEUE_STALE", "message": "Command was dropped because it expired before execution.", "details": {}}],
                    0.0,
                    self._context(),
                    item.command.get("request_id", item.command.get("id", "")),
                )
                item.event.set()
                continue
            try:
                processed += 1
                self._set_current_command(item)
                self.logger.record("command_received", action=item.command.get("action"), client=item.client)
                response = self.registry.execute(item.command)
                item.response = response
                self.logger.record("command_finished", action=response.get("action"), ok=response.get("ok"), client=item.client)
            except Exception as exc:
                self.last_command_error = {"action": item.command.get("action"), "error": str(exc), "timestamp": _now()}
                self.logger.record(
                    "command_crashed",
                    action=item.command.get("action"),
                    error=str(exc),
                    traceback=traceback.format_exc(),
                )
                item.response = make_response(
                    False,
                    item.command.get("action", "unknown"),
                    None,
                    [],
                    [{"code": "INTERNAL_ERROR", "message": str(exc), "details": {"type": type(exc).__name__}}],
                    0.0,
                    self._context(),
                )
            finally:
                self._set_current_command(None)
                item.event.set()

    def _execute_or_enqueue(self, command: dict[str, Any], client: str) -> dict[str, Any]:
        started = time.perf_counter()
        action = command.get("action", "unknown") if isinstance(command, dict) else "unknown"
        request_id = command.get("request_id", command.get("id", "")) if isinstance(command, dict) else ""
        try:
            normalized = validate_command(command, unsafe_developer_mode=self.unsafe_developer_mode)
            action = normalized.get("action", action)
            request_id = normalized.get("request_id", request_id)
        except ValidationError as exc:
            self._checkpoint("validation_failed", started, action=action, request_id=request_id, client=client, error=exc.code)
            return make_response(False, action, None, [], [{"code": exc.code, "message": str(exc), "details": exc.details}], started, self._context(), request_id)
        if action not in self.registry.actions():
            self._checkpoint("handler_missing", started, action=action, request_id=request_id, client=client)
            return make_response(
                False,
                action,
                None,
                [],
                [{"code": "ACTION_NOT_REGISTERED", "message": f"No handler registered for action: {action}", "details": {"action": action}}],
                started,
                self._context(),
                request_id,
            )

        fast_response = self._execute_fast_command(command, client)
        if fast_response is not None:
            return fast_response

        if self._timer is None:
            self.logger.record("command_received", action=command.get("action"), client=client, mode="direct")
            response = self.registry.execute(command)
            self.logger.record("command_finished", action=response.get("action"), ok=response.get("ok"), client=client, mode="direct")
            return response

        item = QueuedCommand(command=command, client=client, event=threading.Event(), enqueued_at=time.perf_counter())
        self.queue.put(item)
        if not item.event.wait(timeout=120):
            item.cancelled = True
            self.last_command_error = {"action": command.get("action"), "error": "Command timed out inside QGIS.", "timestamp": _now()}
            self.logger.record("command_timeout", action=command.get("action"), client=client)
            return make_response(
                False,
                command.get("action", "unknown"),
                None,
                [],
                [{"code": "COMMAND_TIMEOUT", "message": "Command timed out inside QGIS.", "details": {}}],
                0.0,
                self._context(),
            )
        return item.response or {}

    def _execute_fast_command(self, command: dict[str, Any], client: str) -> dict[str, Any] | None:
        started = time.perf_counter()
        action = command.get("action", "unknown")
        request_id = command.get("request_id", command.get("id", ""))
        fast_actions = {"status", "get_capabilities", "get_bridge_config", "get_logs", "get_recent_errors", "get_qgis_environment"}
        if action not in fast_actions:
            return None
        try:
            self._checkpoint("validation_start", started, action=action, request_id=request_id, client=client)
            normalized = validate_command(command, unsafe_developer_mode=self.unsafe_developer_mode)
            action = normalized["action"]
            request_id = normalized.get("request_id", "")
            self._checkpoint("validation_ok", started, action=action, request_id=request_id, client=client)
            if action == "status":
                data = {
                    "display_name": "SIGMAI",
                    "subtitle": "Secure GIS-AI Interface",
                    "bridge": "online",
                    "host": self.host,
                    "port": self.port,
                    "qgis_version": self.qgis_version,
                    "project_loaded": None,
                    **self.status(),
                }
            elif action == "get_capabilities":
                data = get_capabilities({"developer_mode": self.unsafe_developer_mode, "unsafe_developer_mode": self.unsafe_developer_mode})
                data["registered_actions"] = self.registry.actions()
            elif action == "get_bridge_config":
                data = {
                    "host": self.host,
                    "port": self.port,
                    "token_required": True,
                    "transport": "http_localhost",
                    "endpoints": {"command": "/command", "status": "/status"},
                    "unsafe_developer_mode": self.unsafe_developer_mode,
                    "display_name": "SIGMAI",
                    "subtitle": "Secure GIS-AI Interface",
                    "local_only": True,
                    "queue_size": self.queue.qsize(),
                    "busy": self._current_command_snapshot() is not None,
                }
            elif action == "get_logs":
                tail = max(1, min(int(normalized.get("params", {}).get("tail", 200)), 1000))
                data = {"logs": self.logger.tail(tail), "tail": tail}
            elif action == "get_recent_errors":
                tail = max(1, min(int(normalized.get("params", {}).get("tail", 200)), 1000))
                data = {"errors": filter_error_records(self.logger.tail(tail)), "tail": tail}
            elif action == "get_qgis_environment":
                data = {
                    "qgis_version": self.qgis_version,
                    "python_version": sys.version,
                    "platform": sys.platform,
                    "bridge_fast_path": True,
                    "note": "Fast environment response avoids waiting behind a blocked QGIS command queue.",
                    "plugin_version": "0.1.0",
                    "package_name": __package__.split(".")[0] if __package__ else "sigmai",
                    "log_path": str(self.logger.log_path),
                    "registered_command_count": len(self.registry.actions()),
                }
            else:
                return None
            self._checkpoint("handler_ok", started, action=action, request_id=request_id, client=client)
            response = make_response(True, action, data, [], [], started, self._context(), request_id)
            self.logger.record("command_finished", action=action, ok=True, client=client, mode="fast")
            return response
        except ValidationError as exc:
            self._checkpoint("validation_failed", started, action=action, request_id=request_id, client=client, error=exc.code)
            return make_response(False, action, None, [], [{"code": exc.code, "message": str(exc), "details": exc.details}], started, self._context(), request_id)
        except Exception as exc:
            self.last_command_error = {"action": action, "error": str(exc), "timestamp": _now()}
            self.logger.record("command_crashed", action=action, error=str(exc), traceback=traceback.format_exc(), mode="fast")
            return make_response(False, action, None, [], [{"code": "INTERNAL_ERROR", "message": str(exc), "details": {"type": type(exc).__name__}}], started, self._context(), request_id)

    def _make_handler(self):
        bridge = self

        class RequestHandler(BaseHTTPRequestHandler):
            server_version = "SIGMAI/0.1"

            def do_GET(self):
                if self.path != "/status":
                    self._send_json(404, {"ok": False, "error": "Not found."})
                    return
                if not self._is_authorized():
                    return
                self._send_json(200, {"ok": True, "data": bridge.status()})

            def do_POST(self):
                started = time.perf_counter()
                request_id = ""
                action = "unknown"
                bridge._checkpoint("received_http_post", started, action=action, request_id=request_id, client=self.client_address[0])
                if self.path != "/command":
                    self._send_json(404, {"ok": False, "error": "Not found."})
                    return
                bridge._checkpoint("auth_start", started, action=action, request_id=request_id, client=self.client_address[0])
                if not self._is_authorized():
                    return
                bridge._checkpoint("auth_ok", started, action=action, request_id=request_id, client=self.client_address[0])
                try:
                    bridge._checkpoint("parsed_json_start", started, action=action, request_id=request_id, client=self.client_address[0])
                    length = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(length)
                    command = json.loads(body.decode("utf-8"))
                    action = command.get("action", "unknown") if isinstance(command, dict) else "unknown"
                    request_id = command.get("request_id", command.get("id", "")) if isinstance(command, dict) else ""
                    bridge._checkpoint("parsed_json_ok", started, action=action, request_id=request_id, client=self.client_address[0])
                except Exception:
                    self._send_json(400, make_response(False, "unknown", None, [], [{
                        "code": "BAD_REQUEST",
                        "message": "Request body must be valid JSON.",
                        "details": {},
                    }], 0.0, bridge._context()))
                    return

                bridge._checkpoint("dispatch_start", started, action=action, request_id=request_id, client=self.client_address[0])
                response = bridge._execute_or_enqueue(command, self.client_address[0])
                bridge._checkpoint("response_build_start", started, action=action, request_id=request_id, client=self.client_address[0])
                self._send_json(200 if response.get("ok") else 400, response)
                bridge._checkpoint("response_sent", started, action=action, request_id=request_id, client=self.client_address[0])

            def log_message(self, format, *args):
                bridge.logger.record("http_access", client=self.client_address[0], message=format % args)

            def _is_authorized(self) -> bool:
                client_host = self.client_address[0]
                if not is_localhost(client_host):
                    self._send_json(403, make_response(False, "unknown", None, [], [{
                        "code": "FORBIDDEN_REMOTE_HOST",
                        "message": "Only localhost requests are accepted.",
                        "details": {"client": client_host},
                    }], 0.0, bridge._context()))
                    return False
                if not validate_bearer_header(self.headers.get("Authorization"), bridge.token):
                    self._send_json(401, make_response(False, "unknown", None, [], [{
                        "code": "TOKEN_INVALID",
                        "message": "Invalid or missing bearer token.",
                        "details": {},
                    }], 0.0, bridge._context()))
                    return False
                return True

            def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                try:
                    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
                except Exception as exc:
                    fallback = make_response(False, "unknown", None, [], [{
                        "code": "RESPONSE_SERIALIZATION_ERROR",
                        "message": str(exc),
                        "details": {"type": type(exc).__name__},
                    }], 0.0, bridge._context())
                    data = json.dumps(fallback, ensure_ascii=False, default=str).encode("utf-8")
                    status = 500
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return RequestHandler
