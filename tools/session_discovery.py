from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def session_file_candidates() -> list[Path]:
    candidates = []
    env_file = os.environ.get("SIGMAI_SESSION_FILE")
    if env_file:
        candidates.append(Path(env_file))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        for app_name in ["SIGMAI"]:
            session_dir = Path(local_app_data) / app_name / "sessions"
            candidates.append(session_dir / "current_bridge_session.json")
            candidates.extend(sorted(session_dir.glob("SG-*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if session_dir.exists() else [])
    temp = os.environ.get("TEMP")
    if temp:
        for app_name in ["SIGMAI"]:
            session_dir = Path(temp) / app_name / "sessions"
            candidates.append(session_dir / "current_bridge_session.json")
            candidates.extend(sorted(session_dir.glob("SG-*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if session_dir.exists() else [])
            candidates.append(Path(temp) / app_name / "current_bridge_session.json")
        candidates.append(Path(temp) / "sigmai" / "current_bridge_session.json")
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "QGIS" / "QGIS3" / "profiles" / "default" / "python" / "plugins" / "sigmai" / "diagnostics" / "current_bridge_session.json")
    return candidates


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["_session_path"] = str(path)
    return data


def read_session_file(pairing_code: str | None = None, session_file: str | None = None) -> dict[str, Any]:
    if session_file:
        try:
            return _read_json(Path(session_file))
        except Exception:
            return {}
    if pairing_code:
        wanted = pairing_code.upper()
        for path in session_file_candidates():
            if path.stem.upper() == wanted:
                try:
                    return _read_json(path)
                except Exception:
                    return {}
        for path in session_file_candidates():
            try:
                data = _read_json(path)
                if str(data.get("session_id", "")).upper() == wanted or str(data.get("pairing_code", "")).upper() == wanted:
                    return data
            except Exception:
                pass
        return {}
    for path in session_file_candidates():
        try:
            if path.exists():
                data = _read_json(path)
                if data.get("active", data.get("running", True)):
                    return data
        except Exception:
            continue
    return {}


def resolve_connection(host: str | None = None, port: int | None = None, token: str | None = None, pairing_code: str | None = None, session_file: str | None = None) -> dict[str, Any]:
    pairing = pairing_code or os.environ.get("SIGMAI_PAIRING_CODE")
    file_path = session_file or os.environ.get("SIGMAI_SESSION_FILE")
    session = read_session_file(pairing, file_path)
    resolved_token = token or os.environ.get("SIGMAI_TOKEN") or session.get("token", "")
    resolved_host = host or os.environ.get("SIGMAI_HOST") or session.get("host", DEFAULT_HOST)
    resolved_port = int(port or os.environ.get("SIGMAI_PORT") or session.get("port", DEFAULT_PORT))
    return {
        "host": resolved_host,
        "port": resolved_port,
        "token": resolved_token,
        "session": session,
        "session_path": session.get("_session_path", ""),
    }
