from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from core.session_paths import (  # type: ignore
        SESSION_SCHEMA_VERSION,
        current_session_file,
        fallback_sessions_dir,
        generate_pairing_code,
        is_safe_session_path,
        pairing_session_file,
        sessions_dir,
    )
except Exception:
    SESSION_SCHEMA_VERSION = "0.3"

    def sessions_dir() -> Path:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or str(Path.home())
        return Path(base) / "SIGMAI" / "sessions"

    def fallback_sessions_dir() -> Path:
        return Path(os.environ.get("TEMP", str(Path.home()))) / "SIGMAI" / "sessions"

    def current_session_file() -> Path:
        return sessions_dir() / "current_bridge_session.json"

    def pairing_session_file(pairing_code: str) -> Path:
        return sessions_dir() / f"{pairing_code.upper()}.json"

    def is_safe_session_path(path: Path) -> bool:
        return ".git" not in {part.lower() for part in path.resolve().parts}

    def generate_pairing_code() -> str:
        import random
        import string

        return "SG-" + "".join(random.choice(string.digits) for _ in range(4)) + "-" + "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(4))

SCHEMA_VERSION = SESSION_SCHEMA_VERSION


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def preferred_session_dir() -> Path:
    return sessions_dir()


def fallback_session_dir() -> Path:
    return fallback_sessions_dir()


def session_file_path() -> Path:
    return current_session_file()


def fallback_session_file_path() -> Path:
    return fallback_session_dir() / "current_bridge_session.json"


def build_session_payload(
    *,
    host: str,
    port: int,
    token: str,
    qgis_version: str,
    plugin_version: str,
    running: bool,
    source: str = "sigmai",
    session_id: str | None = None,
) -> dict[str, Any]:
    code = session_id or generate_pairing_code()
    return {
        "schema_version": SCHEMA_VERSION,
        "host": host,
        "port": int(port),
        "token": token,
        "started_at": utc_now(),
        "expires_at": None,
        "qgis_version": qgis_version,
        "plugin_version": plugin_version,
        "pid": os.getpid(),
        "session_id": code,
        "pairing_code": code,
        "capabilities_url": f"http://{host}:{int(port)}/command",
        "auth_type": "bearer",
        "local_only": True,
        "running": running,
        "active": running,
        "source": source,
    }


def write_session_file(payload: dict[str, Any]) -> Path:
    errors = []
    paths = [session_file_path(), pairing_session_file(str(payload["session_id"])), fallback_session_file_path()]
    for path in paths:
        try:
            if not is_safe_session_path(path):
                raise ValueError(f"Refusing to write session file under .git: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
            return path
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Could not write SIGMAI session file. " + " | ".join(errors))


def invalidate_session_file() -> None:
    for path in list(sessions_dir().glob("SG-*.json")) + [session_file_path(), fallback_session_file_path()]:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                data["running"] = False
                data["active"] = False
                data["stopped_at"] = utc_now()
                path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass


def cleanup_old_sessions(max_files: int = 20) -> None:
    try:
        files = sorted(sessions_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[max_files:]:
            path.unlink(missing_ok=True)
    except Exception:
        pass
